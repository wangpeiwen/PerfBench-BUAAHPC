#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
加速卡监控抽象基类。

将加速卡（DCU / GPU / NPU 等）的监控逻辑从调度平台（SLURM / LSF / Tianhe）中解耦，
使两个维度可以自由组合：SLURM+DCU、SLURM+GPU、SLURM+无卡 等。
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class AcceleratorMonitor(ABC):
    """
    加速卡监控器抽象基类。

    每种加速卡实现须覆盖以下方法：
    - generate_sampler_block: 生成注入到作业脚本中的 bash 采样代码
    - parse_logs:            解析采集日志，返回结构化数据
    - get_summary:           从解析数据中提取汇总指标
    - get_log_subdir:        返回日志子目录名（如 "dcu_logs"）
    """

    @abstractmethod
    def generate_sampler_block(self, output_dir: str, interval: int) -> str:
        """
        生成注入到作业脚本中的 bash 采样代码块。

        无需注入时返回空字符串。

        Args:
            output_dir: 日志输出目录
            interval:   采样间隔（秒）

        Returns:
            str: bash 代码段，可直接拼接到脚本中
        """

    @abstractmethod
    def parse_logs(self, out_dir: str) -> List[Dict]:
        """
        解析采集日志，返回结构化数据列表。

        Args:
            out_dir: 作业输出目录

        Returns:
            list[dict]: 每条记录为一个采样点的一个设备
        """

    @abstractmethod
    def get_summary(self, parsed_data: List[Dict]) -> Optional[Dict]:
        """
        从解析数据中提取汇总指标。

        Args:
            parsed_data: parse_logs() 返回的数据列表

        Returns:
            dict: 汇总指标字典；数据为空时返回 None
        """

    @abstractmethod
    def get_log_subdir(self) -> str:
        """
        返回日志子目录名（如 "dcu_logs"），用于检测日志是否存在。

        Returns:
            str: 子目录名；无日志时返回空字符串
        """
