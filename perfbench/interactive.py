#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Interactive CLI interface for PerfBench.

Provides a user-friendly menu-driven interface for:
1. 应用软件性能评测 (Application Software Performance Testing)
2. 支撑软件性能评测 (Support Software Performance Testing)
"""

import questionary
import os
from pathlib import Path
from perfbench.utils.logger import get_logger

logger = get_logger()


def validate_path(path_str: str, must_exist: bool = True) -> bool:
    """Validate if path exists and is accessible."""
    path = Path(path_str)
    if must_exist and not path.exists():
        logger.error(f"路径不存在: {path_str}")
        return False
    if must_exist and not os.access(path, os.R_OK):
        logger.error(f"路径无读权限: {path_str}")
        return False
    return True


def validate_positive_integer(val: str) -> bool:
    """Validate if value is a positive integer."""
    try:
        num = int(val)
        return num > 0
    except ValueError:
        return False


def get_application_software_config() -> dict:
    """
    Interactive flow for application software performance testing.
    
    Collects:
    1. 应用软件名称 (Application name)
    2. 监控信息输出目录 (Monitoring output directory)
    3. 监控粒度(间隔时间) (Monitoring interval in seconds)
    4. 原始作业提交脚本目录 (Original job submission script path)
    5. 运行平台 (Running platform: Sunway/SLURM)
    """
    config = {}
    
    print("\n" + "="*60)
    print("应用软件性能评测配置")
    print("="*60 + "\n")
    
    # 1. Application name
    # 注：app_name 当前仅用于配置摘要展示，尚未稳定接入报告生成链路
    #     （报告中的 app_name 字段来自作业脚本的 job_name，而非此处输入）。
    config['app_name'] = questionary.text(
        "请输入应用软件名称:",
        validate=lambda x: len(x.strip()) > 0
    ).ask()
    
    # 2. Output directory
    while True:
        output_dir = questionary.path(
            "请输入监控信息输出目录绝对路径:"
        ).ask()
        
        if not output_dir:
            logger.warning("路径不能为空")
            continue
            
        # Create directory if not exists
        try:
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            config['output_dir'] = output_dir
            break
        except Exception as e:
            logger.error(f"无法创建目录: {e}")
            continue
    
    # 3. Monitoring interval
    while True:
        interval = questionary.text(
            "请输入监控粒度(秒数):",
            validate=lambda x: validate_positive_integer(x)
        ).ask()
        if interval:
            config['interval'] = int(interval)
            break
    
    # 4. Job script path
    while True:
        script_path = questionary.path(
            "请输入原始作业提交脚本绝对路径:"
        ).ask()
        
        if not script_path:
            logger.warning("脚本路径不能为空")
            continue
            
        if validate_path(script_path, must_exist=True):
            config['script_path'] = script_path
            break
        else:
            logger.error("脚本文件不存在或无读权限")
            continue
    
    # 5. Platform selection
    platform = questionary.select(
        "请选择运行平台:",
        choices=[
            "SLURM集群",
            "神威集群"
        ]
    ).ask()
    
    config['platform'] = platform
    if platform == "神威集群":
        config['is_sunway'] = True
    else:
        config['is_sunway'] = False
    
    # Optional: Compute precision
    # 注：precision 当前仅用于配置摘要展示，尚未接入执行主流程（脚本改写或效率计算）。
    precision = questionary.select(
        "请选择计算精度(可选):",
        choices=[
            "默认",
            "单精度 (float)",
            "双精度 (double)"
        ]
    ).ask()
    config['precision'] = precision if precision != "默认" else "default"

    # Optional: Node scale
    while True:
        nodes = questionary.text(
            "请输入节点规模(可选，留空表示使用脚本默认值):",
            default=""
        ).ask()

        if not nodes:
            config['nodes'] = None
            break
        elif validate_positive_integer(nodes):
            config['nodes'] = int(nodes)
            break
        else:
            logger.warning("请输入正整数或留空")
            continue

    return config


def get_support_software_config() -> dict:
    """
    Interactive flow for support software performance testing.
    
    Collects:
    1. 待测支撑软件名称 (Support software name)
    2. 监控信息输出目录 (Monitoring output directory)
    3. 监控粒度(间隔时间) (Monitoring interval in seconds)
    4. 待测支撑软件激活命令 (Software activation command)
    5. benchmark作业提交脚本绝对路径 (Benchmark job script path)
    6. 运行平台 (Running platform: Sunway/SLURM)
    """
    config = {}
    
    print("\n" + "="*60)
    print("支撑软件性能评测配置")
    print("="*60 + "\n")
    
    # 1. Support software name
    # 注：software_name 当前仅用于配置摘要展示，尚未接入执行主流程。
    config['software_name'] = questionary.text(
        "请输入待测支撑软件名称:",
        validate=lambda x: len(x.strip()) > 0
    ).ask()
    
    # 2. Output directory
    while True:
        output_dir = questionary.path(
            "请输入监控信息输出目录绝对路径:"
        ).ask()
        
        if not output_dir:
            logger.warning("路径不能为空")
            continue
            
        # Create directory if not exists
        try:
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            config['output_dir'] = output_dir
            break
        except Exception as e:
            logger.error(f"无法创建目录: {e}")
            continue
    
    # 3. Monitoring interval
    while True:
        interval = questionary.text(
            "请输入监控粒度(秒数):",
            validate=lambda x: validate_positive_integer(x)
        ).ask()
        if interval:
            config['interval'] = int(interval)
            break
    
    # 4. Software activation command
    # 注：activation_cmd 当前仅用于配置摘要展示，尚未接入脚本改写或命令执行链路。
    config['activation_cmd'] = questionary.text(
        "请输入待测支撑软件激活命令(例: 'module load software_name'):",
        validate=lambda x: len(x.strip()) > 0
    ).ask()
    
    # 5. Benchmark job script path
    while True:
        script_path = questionary.path(
            "请输入benchmark作业提交脚本绝对路径:"
        ).ask()
        
        if not script_path:
            logger.warning("脚本路径不能为空")
            continue
            
        if validate_path(script_path, must_exist=True):
            config['benchmark_script'] = script_path
            break
        else:
            logger.error("脚本文件不存在或无读权限")
            continue
    
    # 6. Platform selection
    platform = questionary.select(
        "请选择运行平台:",
        choices=[
            "SLURM集群",
            "神威集群"
        ]
    ).ask()
    
    config['platform'] = platform
    if platform == "神威集群":
        config['is_sunway'] = True
    else:
        config['is_sunway'] = False
    
    # Optional: Compute precision
    # 注：precision 当前仅用于配置摘要展示，尚未接入执行主流程（脚本改写或效率计算）。
    precision = questionary.select(
        "请选择计算精度(可选):",
        choices=[
            "默认",
            "单精度 (float)",
            "双精度 (double)"
        ]
    ).ask()
    config['precision'] = precision if precision != "默认" else "default"

    # Optional: Node scale
    while True:
        nodes = questionary.text(
            "请输入节点规模(可选，留空表示使用脚本默认值):",
            default=""
        ).ask()

        if not nodes:
            config['nodes'] = None
            break
        elif validate_positive_integer(nodes):
            config['nodes'] = int(nodes)
            break
        else:
            logger.warning("请输入正整数或留空")
            continue

    return config


def show_config_summary(config: dict, test_type: str):
    """Display configuration summary for review."""
    print("\n" + "="*60)
    print("配置信息确认")
    print("="*60 + "\n")
    
    if test_type == "application":
        print(f"测试类型: 应用软件性能评测")
        print(f"应用软件名称: {config.get('app_name', 'N/A')}")
    else:
        print(f"测试类型: 支撑软件性能评测")
        print(f"支撑软件名称: {config.get('software_name', 'N/A')}")
        print(f"激活命令: {config.get('activation_cmd', 'N/A')}")
    
    print(f"输出目录: {config.get('output_dir', 'N/A')}")
    print(f"监控间隔(秒): {config.get('interval', 'N/A')}")
    
    if test_type == "application":
        print(f"脚本路径: {config.get('script_path', 'N/A')}")
    else:
        print(f"Benchmark脚本: {config.get('benchmark_script', 'N/A')}")
    
    print(f"运行平台: {config.get('platform', 'N/A')}")
    print(f"计算精度: {config.get('precision', 'N/A')}")
    print(f"节点规模: {config.get('nodes', '使用脚本默认值')}")
    print()


def interactive_main():
    """Main interactive CLI entry point."""
    print("\n" + "="*60)
    print("欢迎使用 PerfBench 性能评测工具 v1.0")
    print("="*60 + "\n")
    
    # Main menu
    test_type = questionary.select(
        "请选择要执行的性能评测类型:",
        choices=[
            "1. 应用软件性能评测",
            "2. 支撑软件性能评测",
            "3. 退出"
        ]
    ).ask()
    
    if test_type is None or "退出" in test_type:
        print("已退出 PerfBench")
        return None
    
    # Collect configuration based on test type
    if "应用软件" in test_type:
        config = get_application_software_config()
        show_config_summary(config, "application")
        config['test_type'] = 'application'
    else:
        config = get_support_software_config()
        show_config_summary(config, "support")
        config['test_type'] = 'support'
    
    # Confirm execution
    proceed = questionary.confirm(
        "确认开始执行性能评测?",
        default=True
    ).ask()
    
    if not proceed:
        print("已取消")
        return None
    
    return config
