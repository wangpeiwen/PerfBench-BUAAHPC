#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
平台适配层包入口。

提供工厂函数 get_platform_adapter()，主流程通过该函数获取平台适配器，
无需直接感知 SLURM 或申威的具体实现细节。
"""

from perfbench.adapters.platform.base import PlatformAdapter
from perfbench.adapters.platform.slurm import SlurmAdapter
from perfbench.adapters.platform.sunway import SunwayAdapter
from perfbench.adapters.accelerator.base import AcceleratorMonitor


def get_platform_adapter(is_sunway: bool,
                         accelerator_monitor: AcceleratorMonitor | None = None
                         ) -> PlatformAdapter:
    """
    根据平台标志返回对应的平台适配器实例。

    Args:
        is_sunway:           True 表示申威平台，False 表示 SLURM 平台
        accelerator_monitor: 加速卡监控器实例（仅 SLURM 平台生效），
                             为 None 时不采集加速卡指标

    Returns:
        PlatformAdapter: 对应平台的适配器实例
    """
    if is_sunway:
        return SunwayAdapter()
    return SlurmAdapter(accelerator_monitor=accelerator_monitor)


__all__ = [
    "PlatformAdapter",
    "SlurmAdapter",
    "SunwayAdapter",
    "get_platform_adapter",
]
