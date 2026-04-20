#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
加速卡监控层包入口。

提供工厂函数 get_accelerator_monitor()，根据配置返回对应的加速卡监控器实例。
调度平台（SLURM / Sunway）通过组合方式持有监控器，两个维度完全正交。
"""

from typing import Optional
from perfbench.adapters.accelerator.base import AcceleratorMonitor
from perfbench.adapters.accelerator.none import NullMonitor
from perfbench.adapters.accelerator.dcu import DcuMonitor
from perfbench.adapters.accelerator.matrix import MatrixMonitor


def get_accelerator_monitor(config: Optional[dict]) -> AcceleratorMonitor:
    """
    根据平台配置返回对应的加速卡监控器实例。

    Args:
        config: 平台配置字典，需包含 accelerator_type 字段。
                为 None 时返回 NullMonitor。

    Returns:
        AcceleratorMonitor: 对应的监控器实例
    """
    if config is None:
        return NullMonitor()

    accel_type = config.get("accelerator_type", "none")
    if accel_type == "dcu":
        return DcuMonitor(
            interval=config.get("accelerator_sampling_interval")
        )
    if accel_type == "matrix":
        return MatrixMonitor(
            interval=config.get("accelerator_sampling_interval")
        )
    return NullMonitor()


__all__ = [
    "AcceleratorMonitor",
    "NullMonitor",
    "DcuMonitor",
    "MatrixMonitor",
    "get_accelerator_monitor",
]
