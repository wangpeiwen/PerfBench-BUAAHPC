#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试配置加载器。

支持 YAML 配置文件，加载后统一返回 dict，供编排引擎使用。
"""

import os
from typing import Optional

from perfbench.utils.logger import get_logger

logger = get_logger()

# YAML 为可选依赖
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


def load_test_config(config_path: str) -> Optional[dict]:
    """
    加载测试配置文件（YAML）。

    Args:
        config_path: 配置文件路径（.yaml/.yml）

    Returns:
        配置字典，加载失败返回 None
    """
    if not os.path.isfile(config_path):
        logger.error(f"配置文件不存在: {config_path}")
        return None

    ext = os.path.splitext(config_path)[1].lower()

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            if ext not in (".yaml", ".yml"):
                logger.error(f"不支持的配置文件格式: {ext}（支持 .yaml/.yml）")
                return None
            if not HAS_YAML:
                logger.error(
                    "需要 PyYAML 库来加载 YAML 配置。"
                    "请执行: pip install pyyaml"
                )
                return None
            config = yaml.safe_load(f)
    except Exception as e:
        logger.error(f"配置文件解析失败: {e}")
        return None

    # 基本校验
    if not isinstance(config, dict):
        logger.error("配置文件顶层必须是字典")
        return None

    # 填充默认值
    config = _apply_defaults(config)
    return config


def _apply_defaults(config: dict) -> dict:
    """为缺失字段填充默认值。"""
    # global
    g = config.setdefault("global", {})
    g.setdefault("granularity", "board")
    g.setdefault("repeat", 1)
    g.setdefault("aggregation", "mean")
    g.setdefault("monitor_interval", 60)

    # scaling
    s = config.setdefault("scaling", {})
    s.setdefault("mode", "strong")
    s.setdefault("scales", [1])
    s.setdefault("datasets", [])
    s.setdefault("compute_ratios", [])
    s.setdefault("compute_ratio_method", "")

    # accuracy
    a = config.setdefault("accuracy", {})
    a.setdefault("enabled", False)
    a.setdefault("reference_file", "")
    a.setdefault("output_parser", "")
    a.setdefault("parser_options", {"column": 0, "delimiter": ",", "skip_header": True})
    a.setdefault("metrics", ["absolute_error", "relative_error", "rmse"])
    a.setdefault("thresholds", {})

    # scale compliance
    sc = config.setdefault("scale_compliance", {})
    sc.setdefault("enabled", True)
    sc.setdefault("active_util_threshold", 10.0)
    sc.setdefault("scale_fraction_threshold", 0.8)
    sc.setdefault("coverage_threshold", 0.9)

    # support
    sp = config.setdefault("support", {})
    sp.setdefault("enabled", False)
    sp.setdefault("before_script", "")
    sp.setdefault("after_script", "")
    sp.setdefault("metric_types", ["exec_perf"])
    sp.setdefault("autotune_apps", [])

    # job
    j = config.setdefault("job", {})
    j.setdefault("script", "")
    j.setdefault("node_placeholder", "__NODES__")
    j.setdefault("dataset_placeholder", "__DATASET__")

    return config


def validate_test_config(config: dict) -> list:
    """
    校验配置完整性，返回错误列表（空列表表示通过）。

    Args:
        config: load_test_config() 返回的配置字典

    Returns:
        错误信息列表
    """
    errors = []

    scaling = config.get("scaling", {})
    mode = scaling.get("mode", "strong")
    scales = scaling.get("scales", [])
    global_cfg = config.get("global", {})

    try:
        monitor_interval = int(global_cfg.get("monitor_interval", 60))
        if monitor_interval <= 0:
            errors.append("global.monitor_interval 必须为正整数")
    except (TypeError, ValueError):
        errors.append("global.monitor_interval 必须为正整数")

    if len(scales) < 2:
        errors.append("scaling.scales 至少需要 2 个规模（基准 + 目标）")

    if mode == "weak":
        datasets = scaling.get("datasets", [])
        ratios = scaling.get("compute_ratios", [])
        if datasets and len(datasets) != len(scales):
            errors.append("weak 模式下 datasets 数量必须与 scales 一致")
        if ratios and len(ratios) != len(scales):
            errors.append("weak 模式下 compute_ratios 数量必须与 scales 一致")
        if ratios and ratios and ratios[0] != 1.0:
            errors.append("compute_ratios 第一个元素必须为 1.0（基准）")

    accuracy = config.get("accuracy", {})
    if accuracy.get("enabled"):
        if not accuracy.get("reference_file"):
            errors.append("启用精度测试时 accuracy.reference_file 不能为空")

    scale_compliance = config.get("scale_compliance", {})
    if scale_compliance.get("enabled", True):
        _validate_ratio(
            scale_compliance, "scale_fraction_threshold",
            errors, "scale_compliance.scale_fraction_threshold"
        )
        _validate_ratio(
            scale_compliance, "coverage_threshold",
            errors, "scale_compliance.coverage_threshold"
        )
        try:
            active_threshold = float(
                scale_compliance.get("active_util_threshold", 10.0)
            )
            if active_threshold < 0:
                errors.append("scale_compliance.active_util_threshold 必须不小于 0")
        except (TypeError, ValueError):
            errors.append("scale_compliance.active_util_threshold 必须为数字")

    support = config.get("support", {})
    if support.get("enabled"):
        if not support.get("before_script"):
            errors.append("支撑软件模式下 support.before_script 不能为空")
        if not support.get("after_script"):
            errors.append("支撑软件模式下 support.after_script 不能为空")

    return errors


def _validate_ratio(config: dict, key: str, errors: list, label: str) -> None:
    try:
        value = float(config.get(key))
    except (TypeError, ValueError):
        errors.append(f"{label} 必须为 0 到 1 之间的数字")
        return
    if value < 0 or value > 1:
        errors.append(f"{label} 必须为 0 到 1 之间的数字")
