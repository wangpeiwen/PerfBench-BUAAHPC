#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数值模拟精度计算。

依据：《高性能应用评测指标体系与规范(十四五试行)V1.0》§4.4

支持三种误差指标：
    - 绝对误差 |simulated - reference|
    - 相对误差 |simulated - reference| / |reference| × 100%
    - RMSE    sqrt(mean((simulated - reference)^2))

参照数据格式由用户自定义，通过可插拔的 output_parser 接口解析。
"""

import math
from typing import Callable, List, Optional, Tuple


def absolute_error(simulated: float, reference: float) -> float:
    """绝对误差 = |模拟值 - 参照值|"""
    return abs(simulated - reference)


def relative_error(simulated: float, reference: float) -> Optional[float]:
    """相对误差 = |模拟值 - 参照值| / |参照值| × 100%"""
    if reference == 0:
        return None
    return abs(simulated - reference) / abs(reference) * 100.0


def rmse(simulated_list: List[float], reference_list: List[float]) -> Optional[float]:
    """均方根误差 RMSE = sqrt(mean((s_i - r_i)^2))"""
    n = len(simulated_list)
    if n == 0 or n != len(reference_list):
        return None
    mse = sum((s - r) ** 2 for s, r in zip(simulated_list, reference_list)) / n
    return math.sqrt(mse)


def accuracy_report(simulated_list: List[float],
                    reference_list: List[float],
                    metrics: Optional[List[str]] = None) -> dict:
    """
    批量计算精度指标。

    Args:
        simulated_list: 模拟值列表
        reference_list: 参照值列表
        metrics:        要计算的指标列表，默认全部
                        可选值: "absolute_error", "relative_error", "rmse"

    Returns:
        dict: {
            "count": int,
            "absolute_errors": list or None,
            "relative_errors": list or None,
            "max_absolute_error": float or None,
            "max_relative_error": float or None,
            "mean_absolute_error": float or None,
            "mean_relative_error": float or None,
            "rmse": float or None,
        }
    """
    if metrics is None:
        metrics = ["absolute_error", "relative_error", "rmse"]

    n = len(simulated_list)
    result = {"count": n}

    if "absolute_error" in metrics and n > 0:
        abs_errs = [absolute_error(s, r)
                    for s, r in zip(simulated_list, reference_list)]
        result["absolute_errors"] = abs_errs
        result["max_absolute_error"] = max(abs_errs)
        result["mean_absolute_error"] = sum(abs_errs) / n
    else:
        result["absolute_errors"] = None
        result["max_absolute_error"] = None
        result["mean_absolute_error"] = None

    if "relative_error" in metrics and n > 0:
        rel_errs = [relative_error(s, r)
                    for s, r in zip(simulated_list, reference_list)]
        valid = [e for e in rel_errs if e is not None]
        result["relative_errors"] = rel_errs
        result["max_relative_error"] = max(valid) if valid else None
        result["mean_relative_error"] = (sum(valid) / len(valid)) if valid else None
    else:
        result["relative_errors"] = None
        result["max_relative_error"] = None
        result["mean_relative_error"] = None

    if "rmse" in metrics:
        result["rmse"] = rmse(simulated_list, reference_list)
    else:
        result["rmse"] = None

    return result


# ---------------------------------------------------------------------------
# 可插拔 output_parser 接口
# ---------------------------------------------------------------------------

def parse_column_csv(filepath: str, column: int = 0,
                     delimiter: str = ",", skip_header: bool = True
                     ) -> List[float]:
    """
    从 CSV/TSV 文件中解析指定列的数值。

    Args:
        filepath:    文件路径
        column:      列索引（0-based）
        delimiter:   分隔符
        skip_header: 是否跳过首行

    Returns:
        数值列表
    """
    values = []
    with open(filepath, "r") as f:
        for i, line in enumerate(f):
            if skip_header and i == 0:
                continue
            line = line.strip()
            if not line:
                continue
            parts = line.split(delimiter)
            if column < len(parts):
                try:
                    values.append(float(parts[column].strip()))
                except ValueError:
                    pass
    return values


# output_parser 注册表：名称 → 解析函数
# 用户可通过 platform_config.json 的 output_parser 字段指定
OUTPUT_PARSERS = {
    "column_csv": parse_column_csv,
}


def get_output_parser(name: str) -> Optional[Callable]:
    """根据名称获取 output_parser"""
    return OUTPUT_PARSERS.get(name)
