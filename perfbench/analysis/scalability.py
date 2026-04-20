#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
可扩展性指标计算。

依据：《高性能应用评测指标体系与规范(十四五试行)V1.0》§4.3
      《高性能支撑软件评测指标与评测规范（草稿）》§2.2, §2.3

公式：
    强可扩展并行效率 = (T_M × M) / (T_N × N) × 100%
    弱可扩展并行效率 = (T_M,s1 × M × F_s) / (T_N,s2 × N) × 100%

其中 F_s = C_s2 / C_s1（计算量倍数，由用户提供）
"""

from typing import List, Optional, Tuple


def strong_scaling_efficiency(T_base: float, N_base: int,
                              T_target: float, N_target: int) -> Optional[float]:
    """
    强可扩展并行效率。

    Args:
        T_base:   基准规模运行时间（秒）
        N_base:   基准规模核数（万核或绝对核数，与 N_target 单位一致即可）
        T_target: 目标规模运行时间（秒）
        N_target: 目标规模核数

    Returns:
        并行效率百分比，输入不合法时返回 None
    """
    if T_target <= 0 or N_target <= 0 or T_base <= 0 or N_base <= 0:
        return None
    return (T_base * N_base) / (T_target * N_target) * 100.0


def weak_scaling_efficiency(T_base: float, N_base: int,
                            T_target: float, N_target: int,
                            F_s: float) -> Optional[float]:
    """
    弱可扩展并行效率。

    Args:
        T_base:   基准规模（问题规模 s1）运行时间（秒）
        N_base:   基准规模核数
        T_target: 目标规模（问题规模 s2）运行时间（秒）
        N_target: 目标规模核数
        F_s:      计算量倍数 = C_s2 / C_s1，由用户提供

    Returns:
        并行效率百分比，输入不合法时返回 None
    """
    if T_target <= 0 or N_target <= 0 or T_base <= 0 or N_base <= 0 or F_s <= 0:
        return None
    return (T_base * N_base * F_s) / (T_target * N_target) * 100.0


def speedup(T_base: float, T_target: float) -> Optional[float]:
    """
    加速比 = T_base / T_target

    Args:
        T_base:   基准规模运行时间（秒）
        T_target: 目标规模运行时间（秒）

    Returns:
        加速比倍数，输入不合法时返回 None
    """
    if T_target <= 0 or T_base <= 0:
        return None
    return T_base / T_target


def multi_scale_report(times: List[float], cores: List[int],
                       mode: str = "strong",
                       F_s_list: Optional[List[float]] = None
                       ) -> List[dict]:
    """
    对多组规模数据批量计算可扩展性指标。

    以第一组为基准，依次计算后续各组相对于基准的并行效率和加速比。

    Args:
        times:    各规模的运行时间列表 [T_1, T_2, ..., T_k]
        cores:    各规模的核数列表 [N_1, N_2, ..., N_k]
        mode:     "strong" 或 "weak"
        F_s_list: 弱可扩展模式下各规模的计算量倍数 [1, F_2, ..., F_k]
                  （第一个元素应为 1.0，表示基准自身）

    Returns:
        列表，每个元素为 dict:
        {
            "scale_index": int,
            "cores": int,
            "time": float,
            "speedup": float or None,
            "efficiency": float or None
        }
    """
    if len(times) != len(cores) or len(times) < 1:
        return []

    T_base = times[0]
    N_base = cores[0]
    results = []

    for i in range(len(times)):
        entry = {
            "scale_index": i,
            "cores": cores[i],
            "time": times[i],
            "speedup": None,
            "efficiency": None,
        }

        if i == 0:
            entry["speedup"] = 1.0
            entry["efficiency"] = 100.0
        else:
            entry["speedup"] = speedup(T_base, times[i])
            if mode == "strong":
                entry["efficiency"] = strong_scaling_efficiency(
                    T_base, N_base, times[i], cores[i])
            elif mode == "weak":
                fs = F_s_list[i] if F_s_list and i < len(F_s_list) else 1.0
                entry["efficiency"] = weak_scaling_efficiency(
                    T_base, N_base, times[i], cores[i], fs)

        results.append(entry)

    return results
