#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
平台适配层包入口。

提供工厂函数 get_platform_adapter()，主流程通过该函数获取平台适配器，
无需直接感知 SLURM 或申威的具体实现细节。
"""

from perfbench.platform.base import PlatformAdapter
from perfbench.platform.slurm import SlurmAdapter
from perfbench.platform.sunway import SunwayAdapter


def get_platform_adapter(is_sunway: bool,
                         dcu_monitoring: bool = False,
                         dcu_interval: int | None = None) -> PlatformAdapter:
    """
    根据平台标志返回对应的平台适配器实例。

    Args:
        is_sunway:      True 表示申威平台，False 表示 SLURM 平台
        dcu_monitoring: 是否启用 DCU (hy-smi) 采样（仅 SLURM 平台生效）
        dcu_interval:   DCU 采样间隔（秒），为 None 时使用全局 interval

    Returns:
        PlatformAdapter: 对应平台的适配器实例
    """
    if is_sunway:
        return SunwayAdapter()
    return SlurmAdapter(dcu_monitoring=dcu_monitoring,
                        dcu_interval=dcu_interval)


__all__ = [
    "PlatformAdapter",
    "SlurmAdapter",
    "SunwayAdapter",
    "get_platform_adapter",
]
