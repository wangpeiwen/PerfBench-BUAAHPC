#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
平台适配层包入口。

提供工厂函数 get_platform_adapter()，主流程通过该函数获取平台适配器，
无需直接感知 SLURM 或申威的具体实现细节。
"""

from typing import Optional
from perfbench.adapters.platform.base import PlatformAdapter
from perfbench.adapters.platform.logs import JobLogSummary, PlatformLogParser
from perfbench.adapters.platform.slurm import SlurmAdapter
from perfbench.adapters.platform.sunway import SunwayAdapter
from perfbench.adapters.platform.tianhe import TianheAdapter
from perfbench.adapters.accelerator.base import AcceleratorMonitor


def get_platform_adapter(platform: str = "slurm",
                         accelerator_monitor: Optional[AcceleratorMonitor] = None
                         ) -> PlatformAdapter:
    """
    根据平台名称返回对应的平台适配器实例。

    Args:
        platform:            平台名称，支持 slurm / sunway / tianhe。
        accelerator_monitor: 加速卡监控器实例，为 None 时不采集加速卡指标

    Returns:
        PlatformAdapter: 对应平台的适配器实例
    """
    platform_name = _normalize_platform(platform)
    if platform_name == "sunway":
        return SunwayAdapter()
    if platform_name == "tianhe":
        return TianheAdapter(accelerator_monitor=accelerator_monitor)
    return SlurmAdapter(accelerator_monitor=accelerator_monitor)


def _normalize_platform(platform: str) -> str:
    """规范化平台名称。"""
    platform_name = str(platform or "slurm").strip().lower()
    valid_platforms = {"slurm", "sunway", "tianhe"}
    if platform_name not in valid_platforms:
        raise ValueError(
            f"不支持的平台类型: {platform}. 可选: slurm, sunway, tianhe"
        )
    return platform_name


__all__ = [
    "PlatformAdapter",
    "PlatformLogParser",
    "JobLogSummary",
    "SlurmAdapter",
    "SunwayAdapter",
    "TianheAdapter",
    "get_platform_adapter",
]
