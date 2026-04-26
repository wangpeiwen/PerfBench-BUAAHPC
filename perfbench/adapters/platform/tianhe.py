#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
天河迈创平台适配器。

封装天河自研调度系统命令集：msub（提交）、mqueue（查询）、mdel（删除）。
脚本注释头格式为 #MSUB。
"""

import os
import subprocess
import time
from typing import Optional
from perfbench.adapters.platform.base import PlatformAdapter
from perfbench.adapters.accelerator.base import AcceleratorMonitor
from perfbench.adapters.accelerator.none import NullMonitor
from perfbench.adapters.platform.logs import JobLogSummary, PlatformLogParser
from perfbench.utils.logger import get_logger
from perfbench.utils.monitoring import (
    generate_monitoring_script,
    start_monitoring_on_login,
)

logger = get_logger()


class TianheLogParser(PlatformLogParser):
    """天河调度日志解析占位实现。"""

    def parse_job_logs(self, out_dir: str, interval: int = 0) -> JobLogSummary:
        logger.warning("天河调度日志解析尚未实现")
        return JobLogSummary()


class TianheAdapter(PlatformAdapter):
    """天河迈创平台适配器，封装 msub / mqueue / mdel 命令集合。"""

    def __init__(self, accelerator_monitor: Optional[AcceleratorMonitor] = None):
        """
        Args:
            accelerator_monitor: 加速卡监控器实例，为 None 时使用 NullMonitor
        """
        self.accelerator_monitor = accelerator_monitor or NullMonitor()

    # ------------------------------------------------------------------
    # 脚本准备（提交前逻辑）
    # ------------------------------------------------------------------

    def prepare_script(self, script_path: str, script_info: dict,
                       interval: int, output_dir: str) -> str:
        """
        生成含监控代码的天河作业脚本副本。

        注入环境记录 echo 行及可选的 Matrix 加速卡采样块。

        Returns:
            str: 改写后的脚本路径
        """
        sampler_block = self.accelerator_monitor.generate_sampler_block(
            output_dir, interval
        )
        modified_script = generate_monitoring_script(
            script_path, script_info, interval, output_dir,
            extra_injection=sampler_block,
        )
        logger.info(f"[Tianhe] 监控脚本已生成: {modified_script}")
        return modified_script

    # ------------------------------------------------------------------
    # 作业提交
    # ------------------------------------------------------------------

    def submit_job(self, script_path: str) -> str:
        """
        通过 msub 提交作业，返回 JobID。

        msub 标准输出格式预期: 包含作业 ID 的行（如 "Job <id> submitted" 或纯数字行）。

        Raises:
            RuntimeError: msub 返回非零退出码或命令不存在
        """
        try:
            result = subprocess.run(
                ['msub', script_path],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            if result.returncode != 0:
                raise RuntimeError(f"msub 提交失败: {result.stderr.strip()}")

            # 尝试多种输出格式解析
            output = result.stdout.strip()
            # 格式1: 纯数字行
            for line in output.splitlines():
                line = line.strip()
                if line.isdigit():
                    jobid = line
                    logger.info(f"[Tianhe] 作业已提交, JobID={jobid}")
                    return jobid
            # 格式2: "Job <id> submitted" 或含数字的行
            import re
            match = re.search(r'(\d+)', output)
            if match:
                jobid = match.group(1)
                logger.info(f"[Tianhe] 作业已提交, JobID={jobid}")
                return jobid

            raise RuntimeError(f"msub 输出无法解析 JobID: {output}")
        except FileNotFoundError:
            raise RuntimeError(
                "msub 命令未找到，请确保在天河迈创集群登录节点上运行")

    # ------------------------------------------------------------------
    # 登录节点监控
    # ------------------------------------------------------------------

    def start_monitoring(self, jobid: str, interval: int, output_dir: str) -> int:
        """
        在登录节点后台启动周期采集脚本（mqueue 状态轮询 + 系统指标）。

        Returns:
            int: 监控进程 PID
        """
        pid = start_monitoring_on_login(jobid, interval, output_dir)
        logger.info(f"[Tianhe] 登录节点监控已启动 (pid={pid})")
        return pid

    # ------------------------------------------------------------------
    # 等待作业完成
    # ------------------------------------------------------------------

    def wait_for_job(self, jobid: str, poll_interval: int = 10) -> str:
        """
        轮询 mqueue 等待作业进入终态。

        天河调度系统终态：DONE（正常完成）、EXIT（异常退出）、CANCELLED（取消）。
        当 mqueue 查不到作业时（已从队列移除），视为 COMPLETED。

        Returns:
            str: 作业最终状态
        """
        logger.info(f"[Tianhe] 等待作业 {jobid} 完成...")
        terminal_states = ['DONE', 'EXIT', 'CANCELLED', 'COMPLETED', 'FAILED']

        while True:
            try:
                result = subprocess.run(
                    ['mqueue', '-j', jobid],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                )
                output = result.stdout.strip()

                # 作业已从队列移除 → 已完成
                if not output or 'not found' in output.lower():
                    logger.info(
                        f"[Tianhe] 作业 {jobid} 已从队列移除，视为 COMPLETED")
                    return "COMPLETED"

                # 在输出中查找状态关键字
                for state in terminal_states:
                    if state in output.upper():
                        logger.info(
                            f"[Tianhe] 作业 {jobid} 已结束，状态: {state}")
                        return state

            except FileNotFoundError:
                raise RuntimeError(
                    "mqueue 命令未找到，请确保在天河迈创集群登录节点上运行"
                )
            except Exception as e:
                logger.warning(f"[Tianhe] 查询作业状态时出错: {e}")

            time.sleep(poll_interval)

    # ------------------------------------------------------------------
    # 日志命令名
    # ------------------------------------------------------------------

    def get_log_cmd_name(self) -> str:
        """返回天河平台日志解析使用的命令名称。"""
        return "mqueue"

    def get_log_parser(self) -> TianheLogParser:
        """返回天河平台调度日志解析器。"""
        return TianheLogParser()
