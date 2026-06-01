#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
领域分析层包入口。

提供平台无关的指标计算与配置读取能力。平台调度日志解析已下沉到
perfbench.adapters.platform.*_logs。
"""

from perfbench.analysis.metrics import calculate_parallelism, calculate_efficiency
from perfbench.analysis.config_reader import get_hardware_config
from perfbench.analysis.scale_compliance import (
    aggregate_scale_compliance,
    calculate_scale_compliance,
)

__all__ = [
    "calculate_parallelism",
    "calculate_efficiency",
    "get_hardware_config",
    "calculate_scale_compliance",
    "aggregate_scale_compliance",
]
