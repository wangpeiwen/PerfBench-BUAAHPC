#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""加速器监控器工厂。"""

from typing import Optional

from perfbench.adapters.accelerator.base import AcceleratorMonitor
from perfbench.adapters.accelerator.dcu import DcuMonitor
from perfbench.adapters.accelerator.matrix import MatrixMonitor
from perfbench.adapters.accelerator.none import NullMonitor


def get_accelerator_monitor(config: Optional[dict]) -> AcceleratorMonitor:
    """
    根据命令行显式构造的加速器配置返回监控器。

    Args:
        config: 包含 accelerator_type 和可选 accelerator_sampling_interval
                的字典。None 或未指定类型时返回 NullMonitor。

    Returns:
        AcceleratorMonitor: 加速器监控器实例。
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
    return NullMonitor() # accel_type == "none"


__all__ = [
    "AcceleratorMonitor",
    "NullMonitor",
    "DcuMonitor",
    "MatrixMonitor",
    "get_accelerator_monitor",
]
