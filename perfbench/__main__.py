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
from perfbench.core.script_processor import process_slurm_script
from perfbench.core.validator import validate_environment
from perfbench.utils.logger import setup_logging
from perfbench.utils.progress_bar import StepProgress
from perfbench.utils.result_handler import calculate_parallelism, get_platform_config, Result
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
    parser.add_argument('--wait', action='store_true', help='等待作业结束并在结束后进行后处理（如果适用）')
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
            job_dir, script_info = process_slurm_script(args.script, args.interval, args.output, wait=args.wait)
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
            generate_certificate_for_test(logger, job_dir, script_info, args)
            progress.finish()  # 7. 报告生成完成
            return

        # 如果没有提供任何参数，显示帮助信息
        parser.print_help()

    except Exception as e:
        logger.error(f"执行过程中发生错误: {str(e)}")
        sys.exit(1)

def generate_certificate_for_test(logger, job_dir, script_info, args):
    platform_config = get_platform_config() # 获取平台配置-platform_config.yaml
    from perfbench.utils.system_checker import detect_scheduler
    scheduler_type = detect_scheduler()

    if not platform_config:
        logger.error('未能读取平台配置(platform_config.yaml)，将使用默认值进行计算')
        platform_config = {'platform_name': 'unknown', 'compared_cores': 5, 'compared_run_time': 60}

    parallelism_info = calculate_parallelism(
        platform_name=platform_config['platform_name'],
        node_num=script_info.get('nodes', 1),
        master_cores=script_info.get('master_cores')
    )
    # 如果是 LSF (Sunway)，并且脚本信息包含 master_cores，那么优先根据 master_cores 估算 core_num
    if scheduler_type == 'lsf' and script_info.get('master_cores'):
        try:
            m_cores = int(script_info.get('master_cores', 0))
            nodes = int(script_info.get('nodes', 1))
            core_num = m_cores * 64 * nodes
            parallelism_info = {'core_num': core_num, 'method': f"nodes * master_cores(={m_cores}) * 64"}
        except Exception:
            pass
    if not parallelism_info:
        parallelism_info = {'core_num': 1, 'method': 'unknown'}
    # ensure core_num is a valid integer
    try:
        core_num_val = int(parallelism_info.get('core_num', 1) or 1)
        if core_num_val <= 0:
            core_num_val = 1
        parallelism_info['core_num'] = core_num_val
    except Exception:
        parallelism_info['core_num'] = 1
    logger.info(f"计算得到的并行度: {parallelism_info}")
            
    # 根据调度器决定解析方式
    if scheduler_type == 'lsf':
        # 解析 cnload 位图日志
        from perfbench.utils.result_handler import postprocess_cnload_job
        csv_path = postprocess_cnload_job(job_dir, interval=args.interval)
        cnres = Result(cmd_name='cnload', out_dir=job_dir, interval=args.interval)
        cnres.parse_cnload_bitmap()
        elapsed_time = cnres.get_elapsed_time()
    else:
        # 默认：使用 sacct 解析
        sacct_result = Result(cmd_name="sacct", out_dir=job_dir, interval=args.interval)
        sacct_result.parse_sacct()
        elapsed_time = sacct_result.get_elapsed_time() # 本次作业的运行时间
            
    if not elapsed_time or elapsed_time == 0:
        logger.warning("无法计算效率: elapsed_time 无效")
        para_eff = 0.0
    else:
        try:
            para_eff = float(
                float(platform_config["compared_cores"] * platform_config["compared_run_time"])
                / float((parallelism_info["core_num"] // 10000) * elapsed_time)
            ) * 100
        except Exception as e:
            logger.error(f"计算效率时出错: {e}")
            para_eff = 0.0
            
    report_info = {
        "platform": platform_config["platform_name"],
        "node_num": script_info['nodes'],
        "app_name": script_info['job_name'],
        "core_num": parallelism_info["core_num"],
        "eff": f"{para_eff:.2f}%({platform_config['compared_cores']} Nodes)",
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    generate_certificate(report_info, job_dir)

if __name__ == '__main__':
    main()
    # platform_config = get_platform_config() # 获取平台配置-platform_config.yaml

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
