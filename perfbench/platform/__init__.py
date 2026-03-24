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


def get_platform_adapter(is_sunway: bool) -> PlatformAdapter:
    """
    根据平台标志返回对应的平台适配器实例。

    Args:
        is_sunway: True 表示申威平台，False 表示 SLURM 平台

    Returns:
        PlatformAdapter: 对应平台的适配器实例
    """
    if is_sunway:
        return SunwayAdapter()
    return SlurmAdapter()


__all__ = [
    "PlatformAdapter",
    "SlurmAdapter",
    "SunwayAdapter",
    "get_platform_adapter",
]
