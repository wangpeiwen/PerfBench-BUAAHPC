#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Package entry point for perfbench.

This module contains the CLI parsing and top-level orchestration.
"""
from datetime import datetime
import sys
import argparse
from perfbench.core.initializer import initialize_environment
from perfbench.core.script_processor import process_slurm_script
from perfbench.core.validator import validate_environment
from perfbench.utils.logger import setup_logging
from perfbench.utils.progress_bar import StepProgress
from perfbench.report.certificate_generator import generate_certificate


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

    # CLI主流程进度条步骤
    steps = [
        "读取用户提交脚本",
        "监控脚本生成中",
        "作业提交",
        "监控中",
        "监控完成",
        "报告生成中",
        "报告生成完成"
    ]
    progress = StepProgress(steps)

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
            progress.next()  # 1. 读取用户提交脚本
            # 解析和生成监控脚本
            progress.next("监控脚本生成中")  # 2. 监控脚本生成中
            # process_slurm_script 内部包含所有后续步骤（除了报告生成）
            job_dir, script_info = process_slurm_script(args.script, args.interval, args.output)
            """
            info = {
                'job_name': None,
                'nodes': 1,
                'tasks_per_node': 1,
                'cpus_per_task': 1,
                'time_limit': None,
                'partition': None,
                'output': None,
                'error': None,
                'commands': []
            }
            """
            progress.next("作业提交")  # 3. 作业提交
            # 监控中（此处为启动监控脚本后）
            progress.next("监控中")  # 4. 监控中
            # 监控完成（此处可根据后处理或监控脚本退出信号完善）
            progress.next("监控完成")  # 5. 监控完成
            logger.info(f"PerfBench流程已完成，输出目录: {job_dir}")
            progress.next("报告生成中")  # 6. 报告生成中
            # TODO: 生成报告
            report_info = {
                "platform": "HYGON",
                "node_num": script_info['nodes'],
                "app_name": script_info['job_name'],
                "core_num": str(int(script_info['nodes']) * int(script_info['tasks_per_node']) * int(script_info['cpus_per_task'])),
                "eff": "18.30%(10 Nodes)",
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            generate_certificate(report_info, job_dir)
            progress.finish()  # 7. 报告生成完成
            return

        # 如果没有提供任何参数，显示帮助信息
        parser.print_help()

    except Exception as e:
        logger.error(f"执行过程中发生错误: {str(e)}")
        sys.exit(1)


if __name__ == '__main__':
    main()
