#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
平台配置读取器。

职责：读取并校验 platform_config.json，返回平台配置字典。
不承担计算逻辑，也不依赖日志文件或调度命令。

配置文件字段说明：
    platform_name:      平台标识字符串（用于 calculate_parallelism 的平台匹配）
    compared_cores:     效率计算基准节点数
    compared_run_time:  效率计算基准运行时间（秒）
"""

import json
from pathlib import Path
from typing import Optional
from perfbench.utils.logger import get_logger

logger = get_logger()


def get_platform_config() -> Optional[dict]:
    """
    从 platform_config.json 中读取平台配置信息。

    配置文件位置固定为 perfbench/ 包根目录下的 platform_config.json，
    该文件是运行时唯一的主配置来源（platform_config.yaml 为冗余副本）。

    Returns:
        dict: 包含 platform_name / compared_cores / compared_run_time 的配置字典；
              读取失败时返回 None。
    """
    try:
        # 定位：从本文件（perfbench/analysis/config_reader.py）向上两级到 perfbench/
        config_path = Path(__file__).resolve().parent.parent / 'platform_config.json'

        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        logger.info(f"已加载平台配置: {config_path}")
        return config

    except FileNotFoundError:
        config_path = Path(__file__).resolve().parent.parent / 'platform_config.json'
        logger.error(f"平台配置文件不存在: {config_path}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"解析 JSON 配置文件失败: {e}")
        return None
    except Exception as e:
        logger.error(f"读取配置文件时发生未知错误: {e}")
        return None
