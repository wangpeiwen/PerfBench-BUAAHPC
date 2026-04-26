#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
平台调度日志解析抽象。

平台适配器负责生成调度日志，也负责提供对应解析器。上层分析和报告
只消费统一的 JobLogSummary，不感知 sacct / bjobs 等具体命令格式。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class JobLogSummary:
    """一次作业调度日志解析后的统一摘要。"""

    job_id: Optional[str] = None
    job_name: Optional[str] = None
    final_state: Optional[str] = None
    elapsed_seconds: Optional[int] = None
    samples: List[Dict] = field(default_factory=list)


class PlatformLogParser(ABC):
    """平台调度日志解析器基类。"""

    @abstractmethod
    def parse_job_logs(self, out_dir: str, interval: int = 0) -> JobLogSummary:
        """
        解析作业调度日志。

        Args:
            out_dir: 作业输出目录
            interval: 监控采集间隔（秒），需要估算运行时间的平台可使用

        Returns:
            JobLogSummary: 统一调度日志摘要
        """

    def parse_resource_logs(self, out_dir: str) -> Dict:
        """解析平台资源日志。默认无结构化资源日志。"""
        return {}
