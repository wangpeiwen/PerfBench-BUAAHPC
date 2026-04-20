#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
领域分析层包入口。

将原 utils/result_handler.py 中混杂的三类职责拆分为独立模块：
- log_parser.py:    日志解析器（Result 类）
- metrics.py:       指标计算器（parallelism / efficiency）
- config_reader.py: 平台配置读取器（get_platform_config）

外部代码可直接从本包导入，也可从 utils/result_handler.py 导入（向后兼容）。
"""

from perfbench.analysis.log_parser import Result
from perfbench.analysis.metrics import calculate_parallelism, calculate_efficiency
from perfbench.analysis.config_reader import get_platform_config

__all__ = [
    "Result",
    "calculate_parallelism",
    "calculate_efficiency",
    "get_platform_config",
]
