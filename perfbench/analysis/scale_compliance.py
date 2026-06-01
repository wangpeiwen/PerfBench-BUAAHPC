#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scale-compliance metrics from accelerator utilization samples."""

import statistics
from typing import Dict, Iterable, List, Optional


UTILIZATION_KEYS = (
    "dcu_pct",
    "matrix_pct",
    "gpu_pct",
    "accelerator_pct",
    "util_pct",
)


def calculate_scale_compliance(
    records: List[Dict],
    expected_devices: int,
    active_util_threshold: float = 10.0,
    scale_fraction_threshold: float = 0.8,
    coverage_threshold: float = 0.9,
    utilization_key: Optional[str] = None,
) -> Optional[Dict]:
    """
    Compute chip-level scale-compliance evidence.

    A device is active in a sample when utilization >= active_util_threshold.
    A sample is scale-covered when active_devices / expected_devices >=
    scale_fraction_threshold. A run passes when scale coverage reaches
    coverage_threshold.
    """
    if not records or expected_devices <= 0:
        return None

    util_key = utilization_key or _infer_utilization_key(records)
    if not util_key:
        return None

    by_sample: Dict[object, List[float]] = {}
    sampled_nodes = set()
    sampled_devices = set()

    for row in records:
        value = _to_float(row.get(util_key))
        if value is None:
            continue

        sample_key = row.get("sample_idx", row.get("time_stamp"))
        if sample_key is None:
            continue

        by_sample.setdefault(sample_key, []).append(value)

        node = row.get("node")
        if node is not None:
            sampled_nodes.add(node)
        device = _device_id(row)
        if node is not None and device is not None:
            sampled_devices.add((node, device))

    if not by_sample:
        return None

    active_fractions = []
    sampled_devices_per_sample = []
    covered_samples = 0

    for values in by_sample.values():
        active_devices = sum(
            1 for value in values if value >= active_util_threshold
        )
        fraction = active_devices / float(expected_devices)
        active_fractions.append(fraction)
        sampled_devices_per_sample.append(len(values))
        if fraction >= scale_fraction_threshold:
            covered_samples += 1

    sample_count = len(active_fractions)
    coverage = covered_samples / float(sample_count)

    return {
        "expected_devices": expected_devices,
        "sample_count": sample_count,
        "active_sample_count": covered_samples,
        "coverage": coverage,
        "coverage_threshold": coverage_threshold,
        "scale_fraction_threshold": scale_fraction_threshold,
        "active_util_threshold": active_util_threshold,
        "mean_active_fraction": statistics.mean(active_fractions),
        "min_active_fraction": min(active_fractions),
        "max_active_fraction": max(active_fractions),
        "sampled_nodes": len(sampled_nodes),
        "sampled_devices": len(sampled_devices),
        "min_sampled_devices_per_sample": min(sampled_devices_per_sample),
        "max_sampled_devices_per_sample": max(sampled_devices_per_sample),
        "compliance_pass": coverage >= coverage_threshold,
    }


def aggregate_scale_compliance(results: Iterable[Optional[Dict]]) -> Optional[Dict]:
    """Aggregate per-run scale-compliance results for one scale."""
    valid = [item for item in results if item]
    if not valid:
        return None

    pass_count = sum(1 for item in valid if item.get("compliance_pass"))
    coverage_values = [item["coverage"] for item in valid]
    active_values = [item["mean_active_fraction"] for item in valid]

    return {
        "run_count": len(valid),
        "pass_count": pass_count,
        "pass_rate": pass_count / float(len(valid)),
        "compliance_pass": pass_count == len(valid),
        "expected_devices": valid[0].get("expected_devices"),
        "coverage_mean": statistics.mean(coverage_values),
        "coverage_min": min(coverage_values),
        "coverage_max": max(coverage_values),
        "mean_active_fraction": statistics.mean(active_values),
        "min_active_fraction": min(item["min_active_fraction"] for item in valid),
        "max_active_fraction": max(item["max_active_fraction"] for item in valid),
        "sample_count_total": sum(item.get("sample_count", 0) for item in valid),
        "sampled_nodes_max": max(item.get("sampled_nodes", 0) for item in valid),
        "sampled_devices_max": max(item.get("sampled_devices", 0) for item in valid),
        "active_util_threshold": valid[0].get("active_util_threshold"),
        "scale_fraction_threshold": valid[0].get("scale_fraction_threshold"),
        "coverage_threshold": valid[0].get("coverage_threshold"),
    }


def _infer_utilization_key(records: List[Dict]) -> Optional[str]:
    for key in UTILIZATION_KEYS:
        if any(row.get(key) is not None for row in records):
            return key
    return None


def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        if isinstance(value, str):
            value = value.strip().rstrip("%")
        return float(value)
    except (TypeError, ValueError):
        return None


def _device_id(row: Dict) -> Optional[str]:
    for key in ("dcu_id", "device_id", "gpu_id", "accelerator_id"):
        if row.get(key) is not None:
            return str(row[key])
    return None
