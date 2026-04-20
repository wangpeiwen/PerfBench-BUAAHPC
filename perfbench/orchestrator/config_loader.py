#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试配置加载器。

支持 YAML 和 JSON 双格式，自动检测文件扩展名。
加载后统一返回 dict，供编排引擎使用。
"""

import json
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
    加载测试配置文件（YAML 或 JSON）。

    Args:
        config_path: 配置文件路径（.yaml/.yml/.json）

    Returns:
        配置字典，加载失败返回 None
    """
    if not os.path.isfile(config_path):
        logger.error(f"配置文件不存在: {config_path}")
        return None

    ext = os.path.splitext(config_path)[1].lower()

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            if ext in (".yaml", ".yml"):
                if not HAS_YAML:
                    logger.error(
                        "需要 PyYAML 库来加载 YAML 配置。"
                        "请执行: pip install pyyaml"
                    )
                    return None
                config = yaml.safe_load(f)
            elif ext == ".json":
                config = json.load(f)
            else:
                logger.error(f"不支持的配置文件格式: {ext}（支持 .yaml/.yml/.json）")
                return None
    except (json.JSONDecodeError, Exception) as e:
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

    support = config.get("support", {})
    if support.get("enabled"):
        if not support.get("before_script"):
            errors.append("支撑软件模式下 support.before_script 不能为空")
        if not support.get("after_script"):
            errors.append("支撑软件模式下 support.after_script 不能为空")

    return errors
