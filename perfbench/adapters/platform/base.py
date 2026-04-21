#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
平台适配层抽象基类。

定义所有平台（SLURM、申威等）必须实现的接口，
使主流程只面向此接口，而不依赖具体平台的命令细节。
"""

from abc import ABC, abstractmethod
from perfbench.utils.script_parser import parse_slurm_script


class PlatformAdapter(ABC):
    """
    平台适配器抽象基类。

    每个平台实现须覆盖以下五个方法：
    - prepare_script: 提交前的脚本改写/准备（如注入监控 echo）
    - submit_job:     通过平台调度命令提交作业，返回 JobID
    - start_monitoring: 在登录节点启动后台监控脚本
    - wait_for_job:   轮询直到作业终止，返回最终状态字符串
    - get_log_cmd_name: 返回本平台日志解析所用的命令名称（sacct/bjobs）
    """

    @abstractmethod
    def prepare_script(self, script_path: str, script_info: dict,
                       interval: int, output_dir: str) -> str:
        """
        对作业脚本进行提交前处理（如注入环境记录），返回最终要提交的脚本路径。

        Args:
            script_path: 原始脚本路径
            script_info: parse_slurm_script() 返回的脚本信息字典
            interval:    监控采集间隔（秒）
            output_dir:  本次作业的输出目录

        Returns:
            str: 准备好的脚本路径（可能是改写后的副本，也可能是原路径）
        """

    @abstractmethod
    def submit_job(self, script_path: str) -> str:
        """
        通过平台调度命令提交作业。

        Args:
            script_path: 要提交的脚本路径

        Returns:
            str: 作业 ID（JobID）

        Raises:
            RuntimeError: 提交失败或命令不可用时
        """

    @abstractmethod
    def start_monitoring(self, jobid: str, interval: int, output_dir: str) -> int:
        """
        在登录节点后台启动监控脚本。

        Args:
            jobid:      作业 ID
            interval:   采集间隔（秒）
            output_dir: 日志输出目录

        Returns:
            int: 监控进程的 PID
        """

    @abstractmethod
    def wait_for_job(self, jobid: str, poll_interval: int = 10) -> str:
        """
        轮询等待作业完成。

        Args:
            jobid:         作业 ID
            poll_interval: 轮询间隔（秒），默认 10

        Returns:
            str: 作业最终状态字符串（如 COMPLETED / DONE / EXIT）
        """

    @abstractmethod
    def get_log_cmd_name(self) -> str:
        """
        返回本平台日志解析所用的命令名称。

        Returns:
            str: 命令名，如 "sacct" 或 "bjobs"
        """

    def parse_script(self, script_path: str) -> dict:
        """
        解析作业脚本，提取 job_name / nodes 等信息。

        默认使用 SLURM 解析器，申威等平台可覆盖此方法。
        """
        return parse_slurm_script(script_path)

    def capture_final_logs(self, jobid: str, output_dir: str) -> None:
        """
        可选：在作业结束后抓取最终调度日志快照。

        默认不做任何操作；需要该能力的平台适配器可覆盖此方法。

        Args:
            jobid:      作业 ID
            output_dir: 本次作业输出目录
        """
        return None
