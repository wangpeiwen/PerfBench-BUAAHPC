#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
结果处理层（向后兼容导出层）。

原 result_handler.py 中的三类职责已按以下方式拆分到 perfbench/analysis/ 下：
    - 日志解析器  → perfbench/analysis/log_parser.py   (Result 类)
    - 指标计算器  → perfbench/analysis/metrics.py       (calculate_parallelism / calculate_efficiency)
    - 配置读取器  → perfbench/analysis/config_reader.py (get_platform_config)

本文件保留为向后兼容层，所有原有导入路径继续有效：
    from perfbench.utils.result_handler import Result
    from perfbench.utils.result_handler import calculate_parallelism
    from perfbench.utils.result_handler import calculate_efficiency
    from perfbench.utils.result_handler import get_platform_config

新代码推荐直接从 perfbench.analysis 导入：
    from perfbench.analysis import Result, calculate_parallelism, calculate_efficiency, get_platform_config
"""

# 向后兼容重新导出
from perfbench.analysis.log_parser import Result, supported_CMD
from perfbench.analysis.metrics import calculate_parallelism, calculate_efficiency
from perfbench.analysis.config_reader import get_platform_config

__all__ = [
    "Result",
    "supported_CMD",
    "calculate_parallelism",
    "calculate_efficiency",
    "get_platform_config",
]
