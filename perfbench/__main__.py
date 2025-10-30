#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Package entry point for perfbench.

This module contains the CLI parsing and top-level orchestration.
"""
import sys
import argparse
from perfbench.core.initializer import initialize_environment
from perfbench.core.script_processor import process_slurm_script
from perfbench.core.validator import validate_environment
from perfbench.utils.logger import setup_logging


def parse_arguments():
    parser = argparse.ArgumentParser(description='PerfBench - SLURM集群性能基准测试工具')
    parser.add_argument('-init', action='store_true', help='初始化工具环境')
    parser.add_argument('-s', '--script', type=str, help='SLURM脚本路径')
    parser.add_argument('-t', '--interval', type=int, help='性能采集时间间隔（秒）')
    parser.add_argument('-o', '--output', type=str, help='输出目录路径')
    parser.add_argument('-v', action='store_true', help='运行工具适配性测试')
    parser.add_argument('--force', action='store_true', help='跳过 SLURM 环境检测（仅用于调试）')
    parser.add_argument('--version', action='version', version='%(prog)s 1.0.0')
    return parser


def main():
    parser = parse_arguments()
    args = parser.parse_args()
    logger = setup_logging()

    try:
        if args.init:
            initialize_environment(force=args.force)
            return

        if args.v:
            validate_environment(force=args.force)
            return

        if args.script:
            if not args.interval or not args.output:
                logger.error("请提供采集间隔(-t)和输出目录(-o)参数")
                sys.exit(1)
            process_slurm_script(args.script, args.interval, args.output)
            return

        # 如果没有提供任何参数，显示帮助信息
        parser.print_help()

    except Exception as e:
        logger.error(f"执行过程中发生错误: {str(e)}")
        sys.exit(1)


if __name__ == '__main__':
    main()
