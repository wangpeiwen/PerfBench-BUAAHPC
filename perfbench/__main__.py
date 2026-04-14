#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PerfBench 包入口。

职责（仅两类）：
1. 参数解析 / 模式分发：解析 CLI 参数或调用交互模式，产出统一的评测请求参数。
2. 阶段调度：按顺序调用 run_evaluation()（含平台适配器）和报告生成，
             不再持有平台分支细节或结果计算细节。

平台差异已收拢至 perfbench.adapters.platform（SlurmAdapter / SunwayAdapter）。
结果分析已收拢至 perfbench.analysis（log_parser / metrics / config_reader）。
"""

from datetime import datetime
import os
import sys
import argparse
from typing import Optional

from perfbench.core.initializer import initialize_environment
from perfbench.core.validator import validate_environment
from perfbench.core.script_processor import run_evaluation
from perfbench.adapters.platform import get_platform_adapter
from perfbench.adapters.accelerator import get_accelerator_monitor
from perfbench.utils.logger import setup_logging
from perfbench.utils.progress_bar import StepProgress
from perfbench.analysis import (
    Result,
    calculate_parallelism,
    calculate_efficiency,
    get_platform_config,
)
from perfbench.report.certificate_generator import generate_certificate
from perfbench.interactive import interactive_main


# ---------------------------------------------------------------------------
# 参数解析
# ---------------------------------------------------------------------------

def parse_arguments():
    parser = argparse.ArgumentParser(description='PerfBench - 超算集群性能基准测试工具')
    parser.add_argument('-init', action='store_true', help='初始化工具环境')
    parser.add_argument('-s', '--script', type=str, help='作业提交脚本路径')
    parser.add_argument('-t', '--interval', type=int, help='性能采集时间间隔（秒）')
    parser.add_argument('-o', '--output', type=str, help='输出目录路径')
    parser.add_argument('-v', action='store_true', help='运行工具适配性测试')
    parser.add_argument('--force', action='store_true', help='跳过环境检测（仅用于调试）')
    parser.add_argument('-sw', action='store_true', help='指定为申威平台（默认自动检测）')
    parser.add_argument('--accelerator', type=str, default=None,
                        choices=['dcu', 'none'],
                        help='加速卡类型（覆盖 platform_config.json 中的 accelerator_type）')
    parser.add_argument('--accelerator-interval', type=int, default=None,
                        help='加速卡采样间隔（秒），默认使用全局 interval')
    parser.add_argument('--dcu', action='store_true',
                        help='启用 DCU 监控（等价于 --accelerator dcu）')
    parser.add_argument('--dcu-interval', type=int, default=None,
                        help='DCU 采样间隔（秒），等价于 --accelerator-interval')
    parser.add_argument('--version', action='version', version='%(prog)s 1.0.0')
    return parser


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def main():
    parser = parse_arguments()
    args = parser.parse_args()
    logger = setup_logging()

    # 进度条步骤定义
    steps = [
        "读取用户提交脚本",
        "监控脚本生成中",
        "作业提交",
        "监控中",
        "监控完成",
        "报告生成中",
        "报告生成完成",
    ]

    try:
        # ---- 初始化模式 ----
        if args.init:
            initialize_environment(force=args.force)
            return

        # ---- 验证模式 ----
        if args.v:
            validate_environment(force=args.force)
            return

        # ---- CLI 评测模式 ----
        if args.script:
            if not args.interval or not args.output:
                logger.error("请提供采集间隔(-t)和输出目录(-o)参数")
                sys.exit(1)

            script_path = args.script
            interval = args.interval
            output_dir = args.output
            is_sunway = args.sw

            progress = StepProgress(steps)
            progress.next()                        # 1. 读取用户提交脚本
            progress.next("监控脚本生成中")         # 2. 监控脚本生成中

            job_dir, script_info = _run_evaluation(
                script_path, interval, output_dir, is_sunway, progress, logger,
                accelerator_override=args.accelerator or ('dcu' if args.dcu else None),
                accelerator_interval_override=args.accelerator_interval or args.dcu_interval,
            )
            _generate_report(logger, job_dir, script_info, interval, is_sunway)
            progress.finish()                      # 7. 报告生成完成
            return

        # ---- 交互评测模式 ----
        config = interactive_main()
        if config is None:
            return

        # 从交互配置中提取统一的评测参数
        if config['test_type'] == 'application':
            script_path = config['script_path']
        else:
            script_path = config['benchmark_script']

        interval = config['interval']
        output_dir = config['output_dir']
        is_sunway = config['is_sunway']

        progress = StepProgress(steps)
        progress.next()                            # 1. 读取用户提交脚本
        progress.next("监控脚本生成中")             # 2. 监控脚本生成中

        job_dir, script_info = _run_evaluation(
            script_path, interval, output_dir, is_sunway, progress, logger
        )

        # 交互模式：若用户填写了节点规模则覆盖脚本中的值
        if config.get('nodes'):
            script_info['nodes'] = config['nodes']

        _generate_report(logger, job_dir, script_info, interval, is_sunway)
        progress.finish()                          # 7. 报告生成完成

    except Exception as e:
        logger.error(f"执行过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


# ---------------------------------------------------------------------------
# 内部辅助：统一评测执行
# ---------------------------------------------------------------------------

def _run_evaluation(script_path: str, interval: int, output_dir: str,
                    is_sunway: bool, progress, logger,
                    accelerator_override: Optional[str] = None,
                    accelerator_interval_override: Optional[int] = None):
    """
    通过平台适配器执行完整评测链路（提交 → 监控 → 等待）。

    Returns:
        tuple[str, dict]: (job_dir, script_info)
    """
    # 读取平台配置，构建加速卡监控器
    platform_config = get_platform_config()

    # CLI 覆盖：将 accelerator_override 合并到配置副本中
    accel_config = dict(platform_config) if platform_config else {}
    if accelerator_override:
        accel_config["accelerator_type"] = accelerator_override
    if accelerator_interval_override is not None:
        accel_config["accelerator_sampling_interval"] = accelerator_interval_override

    accel_monitor = get_accelerator_monitor(accel_config)
    adapter = get_platform_adapter(is_sunway,
                                   accelerator_monitor=accel_monitor)
    job_dir, script_info = run_evaluation(script_path, interval, output_dir, adapter, progress)

    logger.info(f"PerfBench 流程已完成，输出目录: {job_dir}")
    progress.next("报告生成中")  # 6. 报告生成中

    return job_dir, script_info


# ---------------------------------------------------------------------------
# 内部辅助：报告生成
# ---------------------------------------------------------------------------

def _generate_report(logger, job_dir: str, script_info: dict,
                     interval: int, is_sunway: bool):
    """
    读取平台配置、计算并行度和效率，生成 PDF 证书。

    Args:
        logger:      日志对象
        job_dir:     作业输出目录
        script_info: 脚本解析信息字典
        interval:    监控采集间隔（秒）
        is_sunway:   是否为申威平台
    """
    platform_config = get_platform_config()
    if platform_config is None:
        logger.error("无法读取平台配置，报告生成失败")
        return

    # 根据平台确定日志命令名和平台显示名
    if is_sunway:
        platform_label = "Sunway"
        cmd_name = "bjobs"
    else:
        platform_label = "SLURM"
        cmd_name = "sacct"

    # 计算并行度
    parallelism_info = calculate_parallelism(
        platform_name=platform_config['platform_name'],
        node_num=script_info['nodes'],
    )
    if parallelism_info is None:
        logger.error("并行度计算失败，报告生成失败")
        return
    logger.info(f"计算得到的并行度: {parallelism_info}")

    # 解析日志，提取运行时间
    result = Result(
        cmd_name=cmd_name,
        out_dir=job_dir,
        interval=interval,
        platform=platform_label,
    )
    elapsed_time = result.get_elapsed_time()
    if elapsed_time is None:
        logger.error("无法提取作业运行时间，报告生成失败")
        return

    # 计算效率
    para_eff = calculate_efficiency(platform_config, parallelism_info, elapsed_time)
    if para_eff is None:
        logger.error("效率计算失败，报告生成失败")
        return

    # 组装报告信息并生成 PDF
    report_info = {
        "platform": platform_config["platform_name"],
        "node_num": script_info['nodes'],
        "app_name": script_info['job_name'],
        "core_num": parallelism_info["core_num"],
        "eff": f"{para_eff:.2f}%({platform_config['compared_cores']} Nodes)",
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    # 加速卡监控数据集成（通过 AcceleratorMonitor 解耦）
    accel_monitor = get_accelerator_monitor(platform_config)
    log_subdir = accel_monitor.get_log_subdir()
    if log_subdir and os.path.isdir(os.path.join(job_dir, log_subdir)):
        try:
            parsed_data = accel_monitor.parse_logs(job_dir)
            summary = accel_monitor.get_summary(parsed_data)
            if summary:
                logger.info(
                    f"加速卡监控摘要: avg_util={summary['avg_dcu_pct']:.1f}%, "
                    f"avg_vram={summary['avg_vram_pct']:.1f}%, "
                    f"avg_power={summary['avg_power']:.1f}W, "
                    f"nodes={summary['num_nodes']}"
                )
                report_info["dcu_avg_util"] = f"{summary['avg_dcu_pct']:.1f}%"
                report_info["dcu_avg_vram"] = f"{summary['avg_vram_pct']:.1f}%"
                report_info["dcu_avg_power"] = f"{summary['avg_power']:.1f}W"
                report_info["dcu_avg_temp"] = f"{summary['avg_temp']:.1f}°C"
                report_info["dcu_max_util"] = f"{summary['max_dcu_pct']:.1f}%"
                report_info["dcu_num_nodes"] = summary["num_nodes"]
        except FileNotFoundError:
            logger.warning("加速卡日志目录存在但无日志文件，跳过加速卡分析")
        except Exception as e:
            logger.warning(f"加速卡日志解析失败: {e}")

    logger.info(f"报告信息: {report_info}")
    generate_certificate(report_info, job_dir)


# ---------------------------------------------------------------------------
# 向后兼容：保留原函数名供外部直接调用
# ---------------------------------------------------------------------------

def generate_certificate_for_test(logger, job_dir, script_info, args,
                                   is_sunway=False):
    """
    向后兼容包装，等价于 _generate_report()。

    原签名保留以避免破坏可能存在的外部引用。
    推荐新代码直接调用 _generate_report()。
    """
    _generate_report(
        logger=logger,
        job_dir=job_dir,
        script_info=script_info,
        interval=args.interval,
        is_sunway=is_sunway,
    )


if __name__ == '__main__':
    main()
