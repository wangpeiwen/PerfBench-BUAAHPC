#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
硬件配置读取器。

职责：读取并校验 hardware_config.json，返回硬件配置字典。
不承担计算逻辑，也不依赖日志文件或调度命令。

配置文件字段说明：
    hardware_name:      硬件标识字符串（用于 calculate_parallelism 的硬件匹配）
    compared_cores:     效率计算基准节点数
    compared_run_time:  效率计算基准运行时间（秒）
"""

import json
from pathlib import Path
from typing import Optional
from perfbench.utils.logger import get_logger

logger = get_logger()


def get_hardware_config() -> Optional[dict]:
    """
        读取硬件配置文件 hardware_config.json。
    """
    try:
        # 定位：从本文件（perfbench/analysis/config_reader.py）向上两级到 perfbench/
        config_path = Path(__file__).resolve().parent.parent / 'hardware_config.json'

        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        logger.info(f"已加载硬件配置: {config_path}")
        return config

    except FileNotFoundError:
        config_path = Path(__file__).resolve().parent.parent / 'hardware_config.json'
        logger.error(f"硬件配置文件不存在: {config_path}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"解析 JSON 配置文件失败: {e}")
        return None
    except Exception as e:
        logger.error(f"读取配置文件时发生未知错误: {e}")
        return None
