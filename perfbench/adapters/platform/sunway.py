#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
申威（Sunway）平台适配器。

将原散落在 script_processor.py 和 monitoring.py 中的申威相关逻辑
收拢到此单一适配器，消除主流程中的 if is_sunway 分支。
"""

import re
import subprocess
import time
from perfbench.adapters.platform.base import PlatformAdapter
from perfbench.utils.logger import get_logger
from perfbench.utils.monitoring import start_bjob_monitoring_on_login

logger = get_logger()


class SunwayAdapter(PlatformAdapter):
    """
    申威平台适配器，封装 bsub / bjobs / cnload 等命令集合。

    注：申威平台当前不对提交脚本做改写，直接提交原始脚本。
    SLURM 解析器（parse_slurm_script）被复用做基础字段提取，
    因申威脚本格式与 SLURM 有相似结构，后续可按需替换为专用解析器。
    """

    # ------------------------------------------------------------------
    # 脚本准备（提交前逻辑）
    # ------------------------------------------------------------------

    def prepare_script(self, script_path: str, script_info: dict,
                       interval: int, output_dir: str) -> str:
        """
        申威平台无脚本改写步骤，直接返回原始脚本路径。

        Args:
            script_path: 原始脚本路径（直接提交）
            script_info: 解析得到的脚本信息（本方法不使用）
            interval:    监控间隔（本方法不使用）
            output_dir:  输出目录（本方法不使用）

        Returns:
            str: 原始脚本路径，不做修改
        """
        logger.info(f"[Sunway] 申威平台不做脚本改写，直接提交原始脚本: {script_path}")
        return script_path

    # ------------------------------------------------------------------
    # 作业提交
    # ------------------------------------------------------------------

    def submit_job(self, script_path: str) -> str:
        """
        通过 bsub 提交申威作业，返回 JobID。

        Raises:
            RuntimeError: bsub 返回非零退出码或命令不存在
        """
        try:
            result = subprocess.run(
                ['bsub', script_path],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            if result.returncode != 0:
                raise RuntimeError(f"bsub 提交失败: {result.stderr.strip()}")
            # bsub 输出格式因系统而异，取第一个数字串作为 JobID
            match = re.search(r'(\d+)', result.stdout)
            if not match:
                raise RuntimeError(
                    f"无法从 bsub 输出中提取 JobID: {result.stdout.strip()}"
                )
            jobid = match.group(1)
            logger.info(f"[Sunway] 申威作业已提交, JobID={jobid}")
            return jobid
        except FileNotFoundError:
            raise RuntimeError("bsub 命令未找到，请确保在申威集群登录节点上运行")

    # ------------------------------------------------------------------
    # 登录节点监控
    # ------------------------------------------------------------------

    def start_monitoring(self, jobid: str, interval: int, output_dir: str) -> int:
        """
        在登录节点后台启动 bjobs / cnload 周期采集脚本。

        Returns:
            int: 监控进程 PID
        """
        pid = start_bjob_monitoring_on_login(jobid, interval, output_dir)
        logger.info(f"[Sunway] 登录节点申威监控已启动 (pid={pid})")
        return pid

    # ------------------------------------------------------------------
    # 等待作业完成
    # ------------------------------------------------------------------

    def wait_for_job(self, jobid: str, poll_interval: int = 10) -> str:
        """
        轮询 bjobs 等待作业进入终态（DONE / EXIT / CANCELED / TERM）。

        Returns:
            str: 作业最终状态
        """
        logger.info(f"[Sunway] 等待申威作业 {jobid} 完成...")
        while True:
            try:
                result = subprocess.run(
                    ['bjobs', '-noheader', '-o', 'stat', jobid],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                )
                state = result.stdout.strip()
                if any(s in state for s in ['DONE', 'EXIT', 'CANCELED', 'TERM']):
                    logger.info(f"[Sunway] 申威作业 {jobid} 已结束，状态: {state}")
                    return state
            except Exception as e:
                logger.warning(f"[Sunway] 查询申威作业状态时出错: {e}")
            time.sleep(poll_interval)

    # ------------------------------------------------------------------
    # 日志命令名
    # ------------------------------------------------------------------

    def get_log_cmd_name(self) -> str:
        """返回申威平台日志解析使用的命令名称。"""
        return "bjobs"
