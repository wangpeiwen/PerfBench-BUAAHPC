#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
指标计算器。

职责：根据平台类型和节点数计算并行度，根据基准参数计算并行效率。
不依赖文件系统、调度命令或平台配置文件，所有输入均为已解析的 Python 对象。

并行度换算规则说明（硬编码于此，来源为各平台硬件规格）：
    SW26010:       每节点 260 核
    SW39000:       每节点 390 核
    飞腾-64:        每节点 64 核
    Matrix2000:    每节点 256 核
    Matrix3000:    每节点 1648 核
    DCU Z100/Z100L: 每节点 256 DCU核 + 32 CPU核
    BW1000(80CU):  每节点 320 DCU核 + 32 CPU核
    BW1000(88CU):  每节点 352 DCU核 + 32 CPU核
    Tesla P100:    每节点 112 核
    Tesla V100:    每节点 160 核
    Tesla As100:   每节点 216 核

效率计算公式：
    efficiency = (compared_cores × compared_run_time × 10000)
                 / (core_num × elapsed_time) × 100
    其中 10000 为基准规模常数（与 compared_cores 的业务单位关联，
    后续可通过将其纳入 platform_config.json 消除硬编码）。
"""

from perfbench.utils.logger import get_logger

logger = get_logger()


def calculate_parallelism(platform_name: str, node_num: int) -> dict | None:
    """
    根据平台类型和节点数计算并行度。

    Args:
        platform_name: 平台标识字符串，需与 platform_config.json 中的
                       platform_name 字段一致
        node_num:      参与计算的节点数

    Returns:
        dict: {
            "core_num": int,   总核心数
            "method":   str,   计算方式描述（LaTeX 格式）
        }
        不支持的平台返回 None。
    """
    res = {"core_num": None, "method": None}

    # 申威系列
    if platform_name == "SW26010":
        res["core_num"] = node_num * 260
        res["method"] = r"node\_num \times 260"
    elif platform_name == "SW39000":
        res["core_num"] = node_num * 390
        res["method"] = r"node\_num \times 390"

    # 飞腾系列
    elif platform_name == "飞腾-64":
        res["core_num"] = node_num * 64
        res["method"] = r"node\_num \times 64"

    # Matrix 系列
    elif platform_name == "Matrix2000":
        res["core_num"] = node_num * 256
        res["method"] = r"node\_num \times 256"
    elif platform_name == "Matrix3000":
        res["core_num"] = node_num * 1648
        res["method"] = r"node\_num \times 1648"

    # DCU 系列
    elif platform_name in ["DCU Z100", "DCU Z100L"]:
        res["core_num"] = node_num * (256 + 32)
        res["method"] = r"node\_num \times (4\times DCU\_nums + CPU\_nums)"
    elif platform_name == "BW1000(80CU)":
        res["core_num"] = node_num * (320 + 32)
        res["method"] = r"node\_num \times (4\times DCU\_nums + CPU\_nums)"
    elif platform_name == "BW1000(88CU)":
        res["core_num"] = node_num * (352 + 32)
        res["method"] = r"node\_num \times (4\times DCU\_nums + CPU\_nums)"

    # Tesla GPU 系列
    elif platform_name == "Tesla P100":
        res["core_num"] = node_num * 112
        res["method"] = r"node\_num \times 112"
    elif platform_name == "Tesla V100":
        res["core_num"] = node_num * 160
        res["method"] = r"node\_num \times 160"
    elif platform_name == "Tesla As100":
        res["core_num"] = node_num * 216
        res["method"] = r"node\_num \times 216"

    else:
        logger.error(
            f"无法计算并行度：不支持的平台类型。"
            f"platform_name={platform_name!r}, node_num={node_num}"
        )
        return None

    return res


def calculate_efficiency(platform_config: dict, parallelism_info: dict,
                         elapsed_time: int) -> float | None:
    """
    计算并行效率（百分比）。

    公式：
        efficiency = (compared_cores × compared_run_time × 10000)
                     / (core_num × elapsed_time) × 100

    Args:
        platform_config:  平台配置字典，需包含 compared_cores / compared_run_time
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
        compared_cores = platform_config.get("compared_cores", 5)
        compared_run_time = platform_config.get("compared_run_time", 60)
        core_num = parallelism_info["core_num"]

        # 效率 = (基准配置性能) / (当前配置性能) × 100
        # 10000 为基准规模常数，与 compared_cores 的业务单位关联
        efficiency = (
            float(compared_cores * compared_run_time * 10000)
            / float(core_num * elapsed_time)
            * 100
        )
        return efficiency

    except (KeyError, TypeError, ZeroDivisionError) as e:
        logger.error(f"效率计算失败: {e}")
        return None
