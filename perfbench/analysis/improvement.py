#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
支撑软件性能提升率计算。

依据：《高性能支撑软件评测指标与评测规范（草稿）》§2.1-§2.5

包含 6 个指标公式：
    1. 执行性能提升率 R_exec       (§2.1.1)
    2. 混合精度性能提升率 R_mixed   (§2.1.2)
    3. 自动调优平均提升率 R_avg     (§2.1.3)
    4. 编译优化性能提升率 R_compile (§2.4)
    5. I/O 性能提升率 R_IO         (§2.5)
    6. 数据处理能力 C              (§2.5)
"""

from typing import List, Optional, Tuple


def execution_improvement(T_before: float, T_after: float) -> Optional[float]:
    """
    执行性能提升率 R_exec = (T_before - T_after) / T_before × 100%

    §2.1.1: 要求 R_exec ≥ 80%

    Args:
        T_before: 原始系统执行时间（秒）
        T_after:  优化后执行时间（秒）
    """
    if T_before <= 0:
        return None
    return (T_before - T_after) / T_before * 100.0


def mixed_precision_improvement(T_non_mixed: float,
                                T_mixed: float) -> Optional[float]:
    """
    混合精度性能提升率 R_mixed = (T_non_mixed - T_mixed) / T_non_mixed × 100%

    §2.1.2: 要求 R_mixed ≥ 80%

    Args:
        T_non_mixed: 非混合精度版本执行时间（秒）
        T_mixed:     混合精度版本执行时间（秒）
    """
    if T_non_mixed <= 0:
        return None
    return (T_non_mixed - T_mixed) / T_non_mixed * 100.0


def autotune_avg_improvement(before_times: List[float],
                             after_times: List[float]
                             ) -> Optional[Tuple[float, List[float]]]:
    """
    自动调优平均性能提升率 R_avg = (1/K) × Σ R_i

    §2.1.3: 要求 R_avg ≥ 5%

    Args:
        before_times: 各应用优化前执行时间 [T_before_1, ..., T_before_K]
        after_times:  各应用优化后执行时间 [T_after_1, ..., T_after_K]

    Returns:
        (R_avg, [R_1, ..., R_K]) 或 None
    """
    K = len(before_times)
    if K == 0 or K != len(after_times):
        return None
    rates = []
    for b, a in zip(before_times, after_times):
        if b <= 0:
            return None
        rates.append((b - a) / b * 100.0)
    return sum(rates) / K, rates


def compile_optimization_improvement(P_before: float,
                                     P_after: float) -> Optional[float]:
    """
    编译优化性能提升率 R_compile = (P_after - P_before) / P_before × 100%

    §2.4: 要求 R_compile ≥ 20%
    注意：此处用性能指标 P（越大越好），分子是 after - before

    Args:
        P_before: 优化前性能指标
        P_after:  优化后性能指标
    """
    if P_before <= 0:
        return None
    return (P_after - P_before) / P_before * 100.0


def io_improvement(T_io_before: float, T_io_after: float) -> Optional[float]:
    """
    I/O 性能提升率 R_IO = (T_IO_before - T_IO_after) / T_IO_before × 100%

    §2.5: 要求 R_IO ≥ 20%

    Args:
        T_io_before: 优化前 I/O 操作时间（秒）
        T_io_after:  优化后 I/O 操作时间（秒）
    """
    if T_io_before <= 0:
        return None
    return (T_io_before - T_io_after) / T_io_before * 100.0


def data_throughput(data_size_bytes: float,
                    elapsed_seconds: float) -> Optional[float]:
    """
    数据处理能力 C = D / T(D)

    §2.5: 单位 bytes/sec

    Args:
        data_size_bytes:  数据规模（字节）
        elapsed_seconds:  处理时间（秒）
    """
    if elapsed_seconds <= 0:
        return None
    return data_size_bytes / elapsed_seconds
