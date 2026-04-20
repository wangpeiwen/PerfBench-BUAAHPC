#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SLURM 平台适配器。

将原散落在 script_processor.py 和 monitoring.py 中的 SLURM 相关逻辑
收拢到此单一适配器，消除主流程中的 if is_sunway 分支。
"""

import os
import subprocess
import time
from typing import Optional
from perfbench.adapters.platform.base import PlatformAdapter
from perfbench.adapters.accelerator.base import AcceleratorMonitor
from perfbench.adapters.accelerator.none import NullMonitor
from perfbench.utils.logger import get_logger
from perfbench.utils.monitoring import (
    generate_monitoring_script,
    start_monitoring_on_login,
)

logger = get_logger()


class SlurmAdapter(PlatformAdapter):
    """SLURM 平台适配器，封装 sbatch / sacct / squeue 等命令集合。"""

    def __init__(self, accelerator_monitor: Optional[AcceleratorMonitor] = None):
        """
        Args:
            accelerator_monitor: 加速卡监控器实例，为 None 时使用 NullMonitor（不采集）
        """
        self.accelerator_monitor = accelerator_monitor or NullMonitor()

    # ------------------------------------------------------------------
    # 脚本准备（提交前逻辑）
    # ------------------------------------------------------------------

    def prepare_script(self, script_path: str, script_info: dict,
                       interval: int, output_dir: str) -> str:
        """
        生成含监控代码的 SLURM 脚本副本，注入环境记录 echo 行及可选的 DCU 采样块。

        Returns:
            str: 改写后的脚本路径（output_dir/modified_script.slurm）
        """
        sampler_block = self.accelerator_monitor.generate_sampler_block(
            output_dir, interval
        )
        modified_script = generate_monitoring_script(
            script_path, script_info, interval, output_dir,
            extra_injection=sampler_block,
        )
        logger.info(f"[SLURM] 监控脚本已生成: {modified_script}")
        return modified_script

    # ------------------------------------------------------------------
    # 作业提交
    # ------------------------------------------------------------------

    def submit_job(self, script_path: str) -> str:
        """
        通过 sbatch 提交作业，返回 JobID。

        Raises:
            RuntimeError: sbatch 返回非零退出码或命令不存在
        """
        try:
            result = subprocess.run(
                ['sbatch', script_path],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            if result.returncode != 0:
                raise RuntimeError(f"sbatch 提交失败: {result.stderr.strip()}")
            # sbatch 标准输出格式: "Submitted batch job 12345"
            jobid = result.stdout.strip().split()[-1]
            logger.info(f"[SLURM] 作业已提交, JobID={jobid}")
            return jobid
        except FileNotFoundError:
            raise RuntimeError("sbatch 命令未找到，请确保在 SLURM 集群登录节点上运行")

    # ------------------------------------------------------------------
    # 登录节点监控
    # ------------------------------------------------------------------

    def start_monitoring(self, jobid: str, interval: int, output_dir: str) -> int:
        """
        在登录节点后台启动 sacct/sinfo/sstat/scontrol 周期采集脚本。

        Returns:
            int: 监控进程 PID
        """
        pid = start_monitoring_on_login(jobid, interval, output_dir)
        logger.info(f"[SLURM] 登录节点监控已启动 (pid={pid})")
        return pid

    # ------------------------------------------------------------------
    # 等待作业完成
    # ------------------------------------------------------------------

    def wait_for_job(self, jobid: str, poll_interval: int = 10) -> str:
        """
        轮询 sacct 等待作业进入终态（COMPLETED / FAILED / CANCELLED / TIMEOUT）。

        Returns:
            str: 作业最终状态
        """
        logger.info(f"[SLURM] 等待作业 {jobid} 完成...")
        while True:
            try:
                result = subprocess.run(
                    ['sacct', '-j', jobid, '-n', '-o', 'State', '-P'],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                )
                state = (result.stdout.strip().split('\n')[0]
                         if result.stdout.strip() else '')
                if any(s in state for s in
                       ['COMPLETED', 'FAILED', 'CANCELLED', 'TIMEOUT']):
                    logger.info(f"[SLURM] 作业 {jobid} 已结束，状态: {state}")
                    return state
            except Exception as e:
                logger.warning(f"[SLURM] 查询作业状态时出错: {e}")
            time.sleep(poll_interval)

    # ------------------------------------------------------------------
    # 日志命令名
    # ------------------------------------------------------------------

    def get_log_cmd_name(self) -> str:
        """返回 SLURM 平台日志解析使用的命令名称。"""
        return "sacct"

    def capture_final_logs(self, jobid: str, output_dir: str) -> None:
        """
        在作业结束后额外抓取一次最终 sacct 快照。

        主要用于短作业开销测试，避免仅依赖周期轮询日志而低估最终 Elapsed。
        """
        final_sacct_path = os.path.join(output_dir, 'final_sacct.log')
        try:
            result = subprocess.run(
                ['sacct', '-j', jobid, '--format=JobID,JobName%20,State,Elapsed,MaxRSS,AllocCPUs', '-P'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            if result.returncode != 0:
                logger.warning(
                    f"[SLURM] 抓取最终 sacct 快照失败 (JobID={jobid}): {result.stderr.strip()}"
                )
                return

            with open(final_sacct_path, 'w', encoding='utf-8') as handle:
                handle.write(result.stdout)
            logger.info(f"[SLURM] 已写入最终 sacct 快照: {final_sacct_path}")
        except FileNotFoundError:
            logger.warning("[SLURM] sacct 命令未找到，跳过最终快照抓取")
        except Exception as e:
            logger.warning(f"[SLURM] 抓取最终 sacct 快照时出错: {e}")
