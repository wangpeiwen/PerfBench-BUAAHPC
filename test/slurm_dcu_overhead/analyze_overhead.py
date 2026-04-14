#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PerfBench 开销测试结果分析脚本

用法: python3 analyze_overhead.py <results_dir>
  results_dir: run_overhead_test.sh 生成的 overhead_results_* 目录

输出: 汇总表格 + 开销百分比 + 统计检验
"""

import os
import sys
import re
import statistics


def parse_elapsed_from_sacct(sacct_path):
    """从 sacct.log 提取主作业的 Elapsed 时间（秒）"""
    with open(sacct_path, 'r') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) >= 4 and not parts[0].endswith('.batch') and not parts[0].endswith('.extern'):
                elapsed_str = parts[3]
                # 格式: HH:MM:SS 或 D-HH:MM:SS
                if '-' in elapsed_str:
                    days, rest = elapsed_str.split('-', 1)
                    h, m, s = rest.split(':')
                    return int(days) * 86400 + int(h) * 3600 + int(m) * 60 + int(s)
                elif ':' in elapsed_str:
                    segs = elapsed_str.split(':')
                    if len(segs) == 3:
                        return int(segs[0]) * 3600 + int(segs[1]) * 60 + int(segs[2])
                    elif len(segs) == 2:
                        return int(segs[0]) * 60 + int(segs[1])
    return None


def parse_elapsed_from_report(report_path):
    """从 PerfBench 的 performance_report.json 提取 elapsed"""
    import json
    with open(report_path, 'r') as f:
        data = json.load(f)
    elapsed = data.get('elapsed_time') or data.get('elapsed')
    if elapsed is not None:
        return float(elapsed)
    return None


def parse_wallclock(timing_path):
    """从 timing.txt 提取端到端 wall clock"""
    with open(timing_path, 'r') as f:
        content = f.read()
    starts = re.findall(r'start=(\d+\.\d+)', content)
    ends = re.findall(r'end=(\d+\.\d+)', content)
    if starts and ends:
        return float(ends[0]) - float(starts[0])
    return None


def collect_results(base_dir):
    """收集所有测试结果"""
    modes = {
        'bare': [],
        'pb_nodcu': [],
        'pb_dcu10': [],
        'pb_dcu2': [],
    }

    for entry in sorted(os.listdir(base_dir)):
        entry_path = os.path.join(base_dir, entry)
        if not os.path.isdir(entry_path):
            continue

        for mode in modes:
            if entry.startswith(mode + '_'):
                elapsed = None

                # 优先从 sacct 取
                sacct_path = os.path.join(entry_path, 'sacct.log')
                if os.path.exists(sacct_path):
                    elapsed = parse_elapsed_from_sacct(sacct_path)

                # PerfBench 模式尝试从 report 取
                if elapsed is None:
                    report_path = os.path.join(entry_path, 'performance_report.json')
                    if os.path.exists(report_path):
                        elapsed = parse_elapsed_from_report(report_path)

                # 兜底用 wall clock
                if elapsed is None:
                    timing_path = os.path.join(entry_path, 'timing.txt')
                    if os.path.exists(timing_path):
                        elapsed = parse_wallclock(timing_path)

                if elapsed is not None:
                    modes[mode].append(elapsed)
                else:
                    print(f"  [WARN] {entry}: 未能提取 elapsed time")
                break

    return modes


def t_test_independent(a, b):
    """简易独立样本 t 检验（不依赖 scipy）"""
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

    print(f"分析目录: {base_dir}\n")
    modes = collect_results(base_dir)

    # 打印汇总
    bare_mean = statistics.mean(modes['bare']) if modes['bare'] else None

    print("=" * 72)
    print(f"{'模式':<20} {'次数':>4} {'均值(s)':>10} {'标准差(s)':>10} {'开销(%)':>10}")
    print("-" * 72)

    labels = {
        'bare': '裸跑 (baseline)',
        'pb_nodcu': 'PerfBench 无DCU',
        'pb_dcu10': 'PerfBench DCU-10s',
        'pb_dcu2': 'PerfBench DCU-2s',
    }

    for mode in ['bare', 'pb_nodcu', 'pb_dcu10', 'pb_dcu2']:
        data = modes[mode]
        n = len(data)
        if n == 0:
            print(f"{labels[mode]:<20} {'0':>4} {'N/A':>10} {'N/A':>10} {'N/A':>10}")
            continue

        mean = statistics.mean(data)
        std = statistics.stdev(data) if n > 1 else 0.0

        if mode == 'bare':
            overhead = 'baseline'
        elif bare_mean and bare_mean > 0:
            overhead = f"{(mean - bare_mean) / bare_mean * 100:+.2f}%"
        else:
            overhead = 'N/A'

        print(f"{labels[mode]:<20} {n:>4} {mean:>10.1f} {std:>10.2f} {overhead:>10}")

    print("=" * 72)

    # t 检验
    if len(modes['bare']) >= 2:
        print("\n--- 统计检验 (vs 裸跑) ---")
        for mode in ['pb_nodcu', 'pb_dcu10', 'pb_dcu2']:
            if len(modes[mode]) >= 2:
                t_stat, df = t_test_independent(modes['bare'], modes[mode])
                if t_stat is not None:
                    print(f"  {labels[mode]}: t={t_stat:.3f}, df={df:.1f}")

    # 结论
    print("\n--- 结论 ---")
    for mode in ['pb_nodcu', 'pb_dcu10', 'pb_dcu2']:
        if modes[mode] and bare_mean and bare_mean > 0:
            overhead_pct = (statistics.mean(modes[mode]) - bare_mean) / bare_mean * 100
            if abs(overhead_pct) < 1:
                verdict = "可忽略"
            elif abs(overhead_pct) < 5:
                verdict = "可接受，建议在报告中注明"
            else:
                verdict = "偏高，建议优化采样策略"
            print(f"  {labels[mode]}: {overhead_pct:+.2f}% -> {verdict}")


if __name__ == '__main__':
    main()
