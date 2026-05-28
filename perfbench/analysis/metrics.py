#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
指标计算器。

职责：根据硬件类型和节点数计算并行度，根据基准参数计算并行效率。
不依赖调度命令或硬件配置文件，所有输入均为已解析的 Python 对象。

并行度换算规则从 hardware_registry.json 配置文件加载，支持动态扩展。

效率计算公式（对标规范）：
    强可扩展并行效率 = (T_M × M) / (T_N × N) × 100%
    其中 M = compared_cores（基准核数），T_M = compared_run_time（基准时间）
         N = core_num（当前核数），T_N = elapsed_time（当前时间）
"""

import json
import os
from typing import Optional

from perfbench.utils.logger import get_logger

logger = get_logger()

# hardware_registry.json 路径（与本模块同级的上层 perfbench/ 目录下）
_REGISTRY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "hardware_registry.json"
)

_registry_cache = None


def _load_registry() -> dict:
    """加载并缓存 hardware_registry.json"""
    global _registry_cache
    if _registry_cache is not None:
        return _registry_cache
    try:
        with open(_REGISTRY_PATH, "r", encoding="utf-8") as f:
            _registry_cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"加载 hardware_registry.json 失败: {e}")
        _registry_cache = {"processors": {}}
    return _registry_cache


def calculate_parallelism(hardware_name: str, node_num: int,
                          granularity: Optional[str] = None) -> Optional[dict]:
    """
    根据硬件类型和节点数计算并行度。

    从 hardware_registry.json 查表获取每节点核数/板卡数，支持动态扩展新平台。

    Args:
        hardware_name: 硬件标识字符串，需与 hardware_config.json 中的
                       hardware_name 字段一致
        node_num:      参与计算的节点数
        granularity:   测试粒度等级，"board"（板卡级，默认）或 "core"（内部核级）
                       为 None 时使用 hardware_registry.json 中的 default_granularity

    Returns:
        dict: {
            "core_num": int,   总并行单元数（板卡数或核数）
            "method":   str,   计算方式描述（LaTeX 格式）
            "granularity": str, 实际使用的粒度
        }
        不支持的硬件返回 None。
    """
    registry = _load_registry()
    processors = registry.get("processors", {})
    spec = processors.get(hardware_name)

    if spec is None:
        logger.error(
            f"无法计算并行度：不支持的硬件类型。"
            f"hardware_name={hardware_name!r}, node_num={node_num}。"
            f"请在 hardware_registry.json 中添加该硬件配置。"
        )
        return None

    if granularity is None:
        granularity = registry.get("default_granularity", "board")

    if granularity == "board":
        units_per_node = spec.get("boards_per_node", 1)
        method_latex = spec.get("method_latex_board",
                                f"node\\_num \\times {units_per_node}")
    else:
        units_per_node = spec["cores_per_node"]
        method_latex = spec.get("method_latex_core",
                                f"node\\_num \\times {units_per_node}")

    return {
        "core_num": node_num * units_per_node,
        "method": method_latex,
        "granularity": granularity,
    }


def calculate_efficiency(hardware_config: dict, parallelism_info: dict,
                         elapsed_time: int) -> Optional[float]:
    """
    计算并行效率（百分比）。

    对标规范公式：
        efficiency = (T_M × M) / (T_N × N) × 100%

    其中：
        M  = compared_cores（基准规模核数）
        T_M = compared_run_time（基准规模运行时间，秒）
        N  = core_num（当前规模核数）
        T_N = elapsed_time（当前规模运行时间，秒）

    Args:
        hardware_config:  硬件配置字典，需包含 compared_cores / compared_run_time
        parallelism_info: calculate_parallelism() 的返回值
        elapsed_time:     实际作业运行时间（秒），需 > 0

    Returns:
        float: 效率百分比；输入不合法时返回 None。
    """
    if not parallelism_info or parallelism_info.get("core_num") is None:
        logger.warning("并行度信息不完整，无法计算效率")
        return None

    if elapsed_time is None or elapsed_time <= 0:
        logger.warning("运行时间不合法，无法计算效率")
        return None

    try:
        compared_cores = hardware_config.get("compared_cores", 5)
        compared_run_time = hardware_config.get("compared_run_time", 60)
        core_num = parallelism_info["core_num"]

        # 规范公式: E = (T_M × M) / (T_N × N) × 100%
        efficiency = (
            float(compared_cores * compared_run_time)
            / float(core_num * elapsed_time)
            * 100.0
        )
        return efficiency

    except (KeyError, TypeError, ZeroDivisionError) as e:
        logger.error(f"效率计算失败: {e}")
        return None
