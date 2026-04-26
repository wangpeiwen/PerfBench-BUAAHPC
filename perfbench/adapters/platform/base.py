#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
平台适配层抽象基类。

定义所有调度平台（SLURM、LSF、天河等）必须实现的接口，
使主流程只面向此接口，而不依赖具体平台的命令细节。
"""

import os
from abc import ABC, abstractmethod
from perfbench.adapters.platform.logs import PlatformLogParser


def write_instrumented_batch_script(
    original_script: str,
    directive_prefix: str,
    output_dir: str,
    output_name: str,
    job_id_env_name: str,
    extra_injection: str = "",
) -> str:
    with open(original_script, 'r') as handle:
        lines = handle.readlines()

    env_setup = (
        f"\n# PerfBench runtime metadata\n"
        f'echo "PerfBench: job started on $(hostname)" > {output_dir}/job_node_info.txt\n'
        f'echo "{job_id_env_name}=${{{job_id_env_name}:-}}" >> {output_dir}/job_node_info.txt\n'
    )
    if extra_injection:
        env_setup += extra_injection

    if not lines or not lines[0].startswith('#!'):
        lines.insert(0, '#!/bin/bash\n')

    last_directive_idx = -1
    for idx, line in enumerate(lines):
        if line.strip().startswith(directive_prefix):
            last_directive_idx = idx

    insert_pos = last_directive_idx + 1 if last_directive_idx != -1 else 1
    lines.insert(insert_pos, env_setup.lstrip())

    output_script = os.path.join(output_dir, output_name)
    with open(output_script, 'w') as handle:
        handle.write(''.join(lines))
    os.chmod(output_script, 0o755)
    return output_script


class PlatformAdapter(ABC):
    """
    平台适配器抽象基类。

    每个平台实现须覆盖以下五个方法：
    - prepare_script: 提交前的脚本改写/准备（如注入监控 echo）
    - submit_job:     通过平台调度命令提交作业，返回 JobID
    - start_monitoring: 在登录节点启动后台监控脚本
    - wait_for_job:   轮询直到作业终止，返回最终状态字符串
    - get_log_cmd_name: 返回本平台日志解析所用的命令名称（sacct/bjobs）
    - get_log_parser: 返回本平台调度日志解析器
    """

    @abstractmethod
    def prepare_script(self, script_path: str, script_info: dict,
                       interval: int, output_dir: str) -> str:
        """
        对作业脚本进行提交前处理（如注入环境记录），返回最终要提交的脚本路径。

        Args:
            script_path: 原始脚本路径
            script_info: parse_script() 返回的脚本信息字典
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

    @abstractmethod
    def get_log_parser(self) -> PlatformLogParser:
        """
        返回本平台调度日志解析器。

        Returns:
            PlatformLogParser: 解析本平台监控日志的对象
        """

    @abstractmethod
    def parse_script(self, script_path: str) -> dict:
        """
        解析作业脚本，提取 job_name / nodes 等信息。

        具体解析规则由各平台适配器实现。
        """

    def capture_final_logs(self, jobid: str, output_dir: str) -> None:
        """
        可选：在作业结束后抓取最终调度日志快照。

        默认不做任何操作；需要该能力的平台适配器可覆盖此方法。

        Args:
            jobid:      作业 ID
            output_dir: 本次作业输出目录
        """
        return None
