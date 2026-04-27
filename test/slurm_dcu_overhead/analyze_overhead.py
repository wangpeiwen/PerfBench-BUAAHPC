#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Analyze SLURM+DCU overhead benchmark results.

The primary metric is SLURM job elapsed time, not end-to-end wall time.
For PerfBench runs this script prefers ``final_sacct.log`` captured by
``--overhead`` and falls back to periodic ``sacct_*.log`` snapshots.
"""

from __future__ import annotations

import glob
import json
import os
import statistics
import sys
from typing import Dict, Iterable, List, Optional, Tuple


MODES = ("bare", "pb_nodcu", "pb_dcu10", "pb_dcu2")
LABELS = {
    "bare": "bare (baseline)",
    "pb_nodcu": "PerfBench no DCU",
    "pb_dcu10": "PerfBench DCU-10s",
    "pb_dcu2": "PerfBench DCU-2s",
}


def parse_elapsed_string(elapsed: str) -> Optional[int]:
    """Parse SLURM Elapsed strings: SS, MM:SS, HH:MM:SS, D-HH:MM:SS."""
    value = str(elapsed).strip()
    if not value:
        return None

    days = 0
    if "-" in value:
        day_text, value = value.split("-", 1)
        try:
            days = int(day_text)
        except ValueError:
            return None

    parts = value.split(":")
    try:
        if len(parts) == 3:
            hours, minutes, seconds = (int(part) for part in parts)
        elif len(parts) == 2:
            hours = 0
            minutes, seconds = (int(part) for part in parts)
        elif len(parts) == 1:
            hours = 0
            minutes = 0
            seconds = int(parts[0])
        else:
            return None
    except ValueError:
        return None

    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def parse_elapsed_from_sacct_file(path: str) -> Optional[int]:
    """Return the top-level job Elapsed value from a pipe-delimited sacct file."""
    with open(path, "r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            parts = line.strip().split("|")
            if len(parts) < 4:
                continue

            jobid = parts[0].strip()
            if (
                not jobid
                or jobid == "JobID"
                or "." in jobid
                or not any(ch.isdigit() for ch in jobid)
            ):
                continue

            elapsed = parse_elapsed_string(parts[3])
            if elapsed is not None:
                return elapsed
    return None


def parse_elapsed_from_report(path: str) -> Optional[float]:
    with open(path, "r", encoding="utf-8", errors="ignore") as handle:
        data = json.load(handle)

    elapsed = data.get("elapsed_time", data.get("elapsed"))
    try:
        return float(elapsed)
    except (TypeError, ValueError):
        return None


def find_elapsed_from_sacct(entry_path: str) -> Optional[float]:
    final_logs = sorted(
        glob.glob(os.path.join(entry_path, "**", "final_sacct.log"), recursive=True)
    )
    for path in final_logs:
        elapsed = parse_elapsed_from_sacct_file(path)
        if elapsed is not None:
            return float(elapsed)

    bare_sacct = os.path.join(entry_path, "sacct.log")
    if os.path.exists(bare_sacct):
        elapsed = parse_elapsed_from_sacct_file(bare_sacct)
        if elapsed is not None:
            return float(elapsed)

    snapshot_logs = sorted(
        glob.glob(os.path.join(entry_path, "**", "sacct_*.log"), recursive=True)
    )
    values = [
        elapsed
        for elapsed in (parse_elapsed_from_sacct_file(path) for path in snapshot_logs)
        if elapsed is not None
    ]
    return float(max(values)) if values else None


def find_elapsed_from_reports(entry_path: str) -> Optional[float]:
    reports = sorted(
        glob.glob(
            os.path.join(entry_path, "**", "performance_report.json"),
            recursive=True,
        )
    )
    for path in reports:
        elapsed = parse_elapsed_from_report(path)
        if elapsed is not None:
            return elapsed
    return None


def collect_results(base_dir: str) -> Dict[str, List[float]]:
    results: Dict[str, List[float]] = {mode: [] for mode in MODES}

    for entry in sorted(os.listdir(base_dir)):
        entry_path = os.path.join(base_dir, entry)
        if not os.path.isdir(entry_path):
            continue

        mode = next((item for item in MODES if entry.startswith(item + "_")), None)
        if mode is None:
            continue

        elapsed = find_elapsed_from_sacct(entry_path)
        if elapsed is None:
            elapsed = find_elapsed_from_reports(entry_path)

        if elapsed is None:
            print(f"[WARN] {entry}: no job elapsed time found")
            continue

        results[mode].append(elapsed)

    return results


def t_test_independent(a: Iterable[float], b: Iterable[float]) -> Tuple[Optional[float], Optional[float]]:
    left = list(a)
    right = list(b)
    n1, n2 = len(left), len(right)
    if n1 < 2 or n2 < 2:
        return None, None

    m1, m2 = statistics.mean(left), statistics.mean(right)
    v1, v2 = statistics.variance(left), statistics.variance(right)
    se = (v1 / n1 + v2 / n2) ** 0.5
    if se == 0:
        return float("inf"), 0.0

    t_stat = (m2 - m1) / se
    numerator = (v1 / n1 + v2 / n2) ** 2
    denominator = 0.0
    if n1 > 1:
        denominator += (v1 / n1) ** 2 / (n1 - 1)
    if n2 > 1:
        denominator += (v2 / n2) ** 2 / (n2 - 1)
    df = numerator / denominator if denominator else 1.0
    return t_stat, df


def print_summary(results: Dict[str, List[float]]) -> None:
    bare_mean = statistics.mean(results["bare"]) if results["bare"] else None

    print("=" * 78)
    print(f"{'mode':<22} {'n':>4} {'mean(s)':>12} {'std(s)':>12} {'overhead':>12}")
    print("-" * 78)

    for mode in MODES:
        data = results[mode]
        if not data:
            print(f"{LABELS[mode]:<22} {0:>4} {'N/A':>12} {'N/A':>12} {'N/A':>12}")
            continue

        mean = statistics.mean(data)
        std = statistics.stdev(data) if len(data) > 1 else 0.0
        if mode == "bare":
            overhead = "baseline"
        elif bare_mean and bare_mean > 0:
            overhead = f"{(mean - bare_mean) / bare_mean * 100:+.2f}%"
        else:
            overhead = "N/A"

        print(f"{LABELS[mode]:<22} {len(data):>4} {mean:>12.1f} {std:>12.2f} {overhead:>12}")

    print("=" * 78)

    if len(results["bare"]) >= 2:
        print("\nWelch t-test vs bare:")
        for mode in MODES[1:]:
            t_stat, df = t_test_independent(results["bare"], results[mode])
            if t_stat is not None:
                print(f"  {LABELS[mode]}: t={t_stat:.3f}, df={df:.1f}")

    if bare_mean and bare_mean > 0:
        print("\nInterpretation:")
        for mode in MODES[1:]:
            if not results[mode]:
                continue
            overhead_pct = (statistics.mean(results[mode]) - bare_mean) / bare_mean * 100
            if abs(overhead_pct) < 1:
                verdict = "negligible"
            elif abs(overhead_pct) < 5:
                verdict = "visible; repeat and check variance"
            else:
                verdict = "large; inspect sampler frequency and cluster noise"
            print(f"  {LABELS[mode]}: {overhead_pct:+.2f}% -> {verdict}")


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: python3 {sys.argv[0]} <overhead_results_dir>")
        sys.exit(1)

    base_dir = sys.argv[1]
    if not os.path.isdir(base_dir):
        print(f"[ERROR] results directory does not exist: {base_dir}")
        sys.exit(1)

    print(f"Results directory: {base_dir}")
    print("Primary metric: SLURM top-level job Elapsed time\n")
    print_summary(collect_results(base_dir))


if __name__ == "__main__":
    main()
