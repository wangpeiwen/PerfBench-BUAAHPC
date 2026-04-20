#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PerfBench 开销测试结果分析脚本。

用法: python3 analyze_overhead.py <results_dir>
  results_dir: run_overhead_test.sh 生成的 overhead_results_* 目录

统计口径:
  - 只使用作业级 job_elapsed_time 计算开销
  - baseline 为 bare run
  - 不使用 timing.txt 中记录的端到端 end-to-end 时间
"""

import glob
import json
import os
import statistics
import sys


MODES = ('bare', 'pb_nodcu', 'pb_dcu10', 'pb_dcu2')
LABELS = {
    'bare': '裸跑 (baseline)',
    'pb_nodcu': 'PerfBench 无DCU',
    'pb_dcu10': 'PerfBench DCU-10s',
    'pb_dcu2': 'PerfBench DCU-2s',
}


def parse_elapsed_string(elapsed_str):
    """将 HH:MM:SS 或 D-HH:MM:SS 解析为秒。"""
    elapsed_str = str(elapsed_str).strip()
    if not elapsed_str:
        return None

    if '-' in elapsed_str:
        days, rest = elapsed_str.split('-', 1)
        parts = rest.split(':')
        if len(parts) != 3:
            return None
        hours, minutes, seconds = parts
        return (
            int(days) * 86400
            + int(hours) * 3600
            + int(minutes) * 60
            + int(seconds)
        )

    parts = elapsed_str.split(':')
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return int(hours) * 3600 + int(minutes) * 60 + int(seconds)
    if len(parts) == 2:
        minutes, seconds = parts
        return int(minutes) * 60 + int(seconds)
    return None


def parse_elapsed_from_sacct_file(sacct_path):
    """从单个 sacct 日志提取主作业 Elapsed 时间（秒）。"""
    with open(sacct_path, 'r', encoding='utf-8', errors='ignore') as handle:
        for line in handle:
            parts = line.strip().split('|')
            if len(parts) < 4:
                continue

            jobid = parts[0]
            if not jobid or jobid.endswith('.batch') or jobid.endswith('.extern'):
                continue

            elapsed = parse_elapsed_string(parts[3])
            if elapsed is not None:
                return elapsed
    return None


def parse_elapsed_from_report(report_path):
    """从 performance_report.json 提取 job_elapsed_time。"""
    with open(report_path, 'r', encoding='utf-8') as handle:
        data = json.load(handle)

    elapsed = data.get('elapsed_time')
    if elapsed is None:
        elapsed = data.get('elapsed')

    if elapsed is None:
        return None

    try:
        return float(elapsed)
    except (TypeError, ValueError):
        return None


def find_elapsed_from_sacct(entry_path):
    """在结果目录中递归查找 sacct 日志，并返回最终 job_elapsed_time。"""
    final_candidates = sorted(
        glob.glob(os.path.join(entry_path, '**', 'final_sacct.log'), recursive=True)
    )
    for sacct_path in final_candidates:
        elapsed = parse_elapsed_from_sacct_file(sacct_path)
        if elapsed is not None:
            return elapsed

    bare_sacct = os.path.join(entry_path, 'sacct.log')
    if os.path.exists(bare_sacct):
        elapsed = parse_elapsed_from_sacct_file(bare_sacct)
        if elapsed is not None:
            return elapsed

    candidates = sorted(
        glob.glob(os.path.join(entry_path, '**', 'sacct_*.log'), recursive=True)
    )

    elapsed_values = []
    for sacct_path in candidates:
        elapsed = parse_elapsed_from_sacct_file(sacct_path)
        if elapsed is not None:
            elapsed_values.append(elapsed)

    if not elapsed_values:
        return None

    # 对周期性采样的 sacct_*.log 取最大值，代表作业完成时的最终 Elapsed。
    return max(elapsed_values)


def find_elapsed_from_reports(entry_path):
    """兼容旧结果目录中的 performance_report.json。"""
    for report_path in sorted(
        glob.glob(os.path.join(entry_path, '**', 'performance_report.json'), recursive=True)
    ):
        elapsed = parse_elapsed_from_report(report_path)
        if elapsed is not None:
            return elapsed
    return None


def collect_results(base_dir):
    """收集所有测试结果。"""
    modes = {mode: [] for mode in MODES}

    for entry in sorted(os.listdir(base_dir)):
        entry_path = os.path.join(base_dir, entry)
        if not os.path.isdir(entry_path):
            continue

        matched_mode = None
        for mode in MODES:
            if entry.startswith(mode + '_'):
                matched_mode = mode
                break

        if matched_mode is None:
            continue

        elapsed = find_elapsed_from_sacct(entry_path)
        if elapsed is None:
            elapsed = find_elapsed_from_reports(entry_path)

        if elapsed is not None:
            modes[matched_mode].append(elapsed)
            continue

        timing_path = os.path.join(entry_path, 'timing.txt')
        if os.path.exists(timing_path):
            print(
                f"  [WARN] {entry}: 未找到 job_elapsed_time；"
                "timing.txt 仅记录 end-to-end 时间，已按设计忽略"
            )
        else:
            print(f"  [WARN] {entry}: 未找到可用的 job_elapsed_time")

    return modes


def t_test_independent(a, b):
    """简易独立样本 t 检验（不依赖 scipy）。"""
    n1, n2 = len(a), len(b)
    if n1 < 2 or n2 < 2:
        return None, None
    m1, m2 = statistics.mean(a), statistics.mean(b)
    v1, v2 = statistics.variance(a), statistics.variance(b)
    se = (v1 / n1 + v2 / n2) ** 0.5
    if se == 0:
        return float('inf'), 0.0
    t_stat = (m2 - m1) / se
    # Welch-Satterthwaite 自由度
    df = (v1 / n1 + v2 / n2) ** 2 / (
        (v1 / n1) ** 2 / (n1 - 1) + (v2 / n2) ** 2 / (n2 - 1)
    ) if (v1 + v2) > 0 else 1
    return t_stat, df


def main():
    if len(sys.argv) < 2:
        print(f"用法: python3 {sys.argv[0]} <overhead_results_dir>")
        sys.exit(1)

    base_dir = sys.argv[1]
    if not os.path.isdir(base_dir):
        print(f"错误: 目录不存在: {base_dir}")
        sys.exit(1)

    print(f"分析目录: {base_dir}")
    print("统计口径: 仅使用 job_elapsed_time；忽略 timing.txt / end-to-end\n")
    modes = collect_results(base_dir)

    bare_mean = statistics.mean(modes['bare']) if modes['bare'] else None

    print("=" * 72)
    print(f"{'模式':<20} {'次数':>4} {'均值(s)':>10} {'标准差(s)':>10} {'开销(%)':>10}")
    print("-" * 72)

    for mode in MODES:
        data = modes[mode]
        n = len(data)
        if n == 0:
            print(f"{LABELS[mode]:<20} {'0':>4} {'N/A':>10} {'N/A':>10} {'N/A':>10}")
            continue

        mean = statistics.mean(data)
        std = statistics.stdev(data) if n > 1 else 0.0

        if mode == 'bare':
            overhead = 'baseline'
        elif bare_mean and bare_mean > 0:
            overhead = f"{(mean - bare_mean) / bare_mean * 100:+.2f}%"
        else:
            overhead = 'N/A'

        print(f"{LABELS[mode]:<20} {n:>4} {mean:>10.1f} {std:>10.2f} {overhead:>10}")

    print("=" * 72)

    if len(modes['bare']) >= 2:
        print("\n--- 统计检验 (vs 裸跑) ---")
        for mode in MODES[1:]:
            if len(modes[mode]) >= 2:
                t_stat, df = t_test_independent(modes['bare'], modes[mode])
                if t_stat is not None:
                    print(f"  {LABELS[mode]}: t={t_stat:.3f}, df={df:.1f}")

    print("\n--- 结论 ---")
    for mode in MODES[1:]:
        if modes[mode] and bare_mean and bare_mean > 0:
            overhead_pct = (statistics.mean(modes[mode]) - bare_mean) / bare_mean * 100
            if overhead_pct <= -1:
                verdict = "低于 baseline，通常说明存在测试波动或统计分辨率差异"
            elif abs(overhead_pct) < 1:
                verdict = "可忽略"
            elif abs(overhead_pct) < 5:
                verdict = "可接受，建议在报告中注明"
            else:
                verdict = "偏高，建议优化采样策略"
            print(f"  {LABELS[mode]}: {overhead_pct:+.2f}% -> {verdict}")


if __name__ == '__main__':
    main()
