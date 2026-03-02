#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Package entry point for perfbench.

This module contains the CLI parsing and top-level orchestration.
"""
from datetime import datetime
import sys
import argparse
import math
from perfbench.core.initializer import initialize_environment
from perfbench.core.script_processor import process_slurm_script, process_sunway_script
from perfbench.core.validator import validate_environment
from perfbench.utils.logger import setup_logging
from perfbench.utils.progress_bar import StepProgress
from perfbench.utils.result_handler import calculate_parallelism, get_platform_config, Result, calculate_efficiency
from perfbench.report.certificate_generator import generate_certificate


def parse_arguments():
    parser = argparse.ArgumentParser(description='PerfBench - 超算集群性能基准测试工具')
    parser.add_argument('-init', action='store_true', help='初始化工具环境')
    parser.add_argument('-s', '--script', type=str, help='作业提交脚本路径')
    parser.add_argument('-t', '--interval', type=int, help='性能采集时间间隔（秒）')
    parser.add_argument('-o', '--output', type=str, help='输出目录路径')
    parser.add_argument('-v', action='store_true', help='运行工具适配性测试')
    parser.add_argument('--force', action='store_true', help='跳过环境检测（仅用于调试）')
    parser.add_argument('-sw', action='sunway_true', help='指定为申威平台（默认自动检测）')
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
            if not args.sw:
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
                generate_certificate_for_test(logger, job_dir, script_info, args, is_sunway=False)
                progress.finish()  # 7. 报告生成完成
                return
            else:
                job_dir, script_info = process_sunway_script(args.script, args.interval, args.output)
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
                generate_certificate_for_test(logger, job_dir, script_info, args, is_sunway=True)
                progress.finish()  # 7. 报告生成完成
                return
        # 如果没有提供任何参数，显示帮助信息
        parser.print_help()

    except Exception as e:
        logger.error(f"执行过程中发生错误: {str(e)}")
        sys.exit(1)


def generate_certificate_for_test(logger, job_dir, script_info, args, is_sunway=False):
    """
    生成性能测试证书
    
    Args:
        logger: 日志对象
        job_dir: 作业输出目录
        script_info: 脚本信息字典
        args: 命令行参数
        is_sunway: 是否为申威平台
    """
    platform_config = get_platform_config()
    
    # 根据平台类型选择相应的日志解析
    if is_sunway:
        platform = "Sunway"
        cmd_name = "bjobs"
    else:
        platform = "SLURM"
        cmd_name = "sacct"
    
    parallelism_info = calculate_parallelism(
        platform_name=platform_config['platform_name'], 
        node_num=script_info['nodes']
    )
    logger.info(f"计算得到的并行度: {parallelism_info}")
    
    # 根据平台类型解析结果
    result = Result(cmd_name=cmd_name, out_dir=job_dir, interval=args.interval, platform=platform)
    elapsed_time = result.get_elapsed_time()
    
    if elapsed_time is None:
        logger.error("无法提取作业运行时间，报告生成失败")
        return
    
    # 计算效率（两个平台使用同一个公式）
    para_eff = calculate_efficiency(platform_config, parallelism_info, elapsed_time)
    
    if para_eff is None:
        logger.error("效率计算失败，报告生成失败")
        return
    
    report_info = {
        "platform": platform_config["platform_name"],
        "node_num": script_info['nodes'],
        "app_name": script_info['job_name'],
        "core_num": parallelism_info["core_num"],
        "eff": f"{para_eff:.2f}%({platform_config['compared_cores']} Nodes)",
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    
    logger.info(f"报告信息: {report_info}")
    generate_certificate(report_info, job_dir)

if __name__ == '__main__':
    main()
    platform_config = get_platform_config() # 获取平台配置-platform_config.yaml

    # parallelism_info = calculate_parallelism(platform_name=platform_config['platform_name'], node_num=100)
    # import os    
    # # 解析sacct结果
    # root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # out_dir = os.path.join(root, "logs")
    # sacct_result = Result(cmd_name="sacct", out_dir=out_dir, interval=2)
    # sacct_result.parse_sacct()
    # elapsed_time = sacct_result.get_elapsed_time() # 本次作业的运行时间
            
    # para_eff = float(
    # float(platform_config["compared_cores"] * platform_config["compared_run_time"])
    #     / float((parallelism_info["core_num"] // 10000) * elapsed_time)
    # ) * 100
            
    # report_info = {
    #     "platform": platform_config["platform_name"],
    #     "node_num": 100,
    #     "app_name": 'LAMMPS',
    #     "core_num": parallelism_info["core_num"],
    #     "eff": f"{para_eff:.2f}%({platform_config['compared_cores']} Nodes)",
    #     "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    # }
    # generate_certificate(report_info, out_dir)
