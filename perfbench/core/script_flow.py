#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Script-mode execution flow for PerfBench."""

import os
from datetime import datetime
from typing import Optional

from perfbench.adapters.accelerator import get_accelerator_monitor
from perfbench.adapters.platform import get_platform_adapter
from perfbench.analysis import (
    calculate_efficiency,
    calculate_parallelism,
    get_hardware_config,
)
from perfbench.core.job_runner import run_evaluation as run_job_evaluation
from perfbench.utils.progress_bar import StepProgress


SCRIPT_FLOW_STEPS = [
    "读取作业提交脚本",
    "生成监控脚本",
    "提交作业",
    "启动监控",
    "等待作业结束",
    "生成报告",
    "报告生成完成",
]


def run_script_flow(args, logger) -> None:
    """Run the single-script evaluation flow."""
    progress = StepProgress(SCRIPT_FLOW_STEPS)
    progress.next()
    progress.next("生成监控脚本")

    job_dir, script_info = _run_evaluation(
        script_path=args.script,
        interval=args.interval,
        output_dir=args.output,
        platform=args.platform,
        progress=progress,
        logger=logger,
        accelerator_type=args.accelerator,
        accelerator_interval=args.accelerator_interval,
        overhead_mode=args.overhead,
    )
    _generate_report(
        logger, job_dir, script_info, args.interval, args.platform,
        _build_accelerator_config(
            accelerator_type=args.accelerator,
            accelerator_interval=args.accelerator_interval,
        ),
    )
    progress.finish()


def _run_evaluation(script_path: str, interval: int, output_dir: str,
                    platform: str, progress, logger,
                    accelerator_type: Optional[str] = None,
                    accelerator_interval: Optional[int] = None,
                    overhead_mode: bool = False):
    accelerator_config = _build_accelerator_config(
        accelerator_type=accelerator_type,
        accelerator_interval=accelerator_interval,
    )

    accel_monitor = get_accelerator_monitor(accelerator_config)
    adapter = get_platform_adapter(platform, accelerator_monitor=accel_monitor)
    job_dir, script_info = run_job_evaluation(
        script_path, interval, output_dir, adapter, progress,
        capture_final_logs=overhead_mode,
    )

    logger.info(f"PerfBench 评测输出目录: {job_dir}")
    progress.next("生成报告")

    return job_dir, script_info


def _build_accelerator_config(accelerator_type: Optional[str] = None,
                              accelerator_interval: Optional[int] = None
                              ) -> dict:
    accelerator_config = {"accelerator_type": accelerator_type or "none"}
    if accelerator_interval is not None:
        accelerator_config["accelerator_sampling_interval"] = accelerator_interval
    return accelerator_config


def _generate_report(logger, job_dir: str, script_info: dict,
                     interval: int, platform: str,
                     accelerator_config: Optional[dict] = None) -> None:
    hardware_config = get_hardware_config()
    if hardware_config is None:
        logger.error("读取硬件配置失败")
        return

    parallelism_info = calculate_parallelism(
        hardware_name=hardware_config["hardware_name"],
        node_num=script_info["nodes"],
    )
    if parallelism_info is None:
        logger.error("并行度计算失败")
        return
    logger.info(f"并行度信息: {parallelism_info}")

    log_parser = get_platform_adapter(platform).get_log_parser()
    log_summary = log_parser.parse_job_logs(job_dir, interval)
    elapsed_time = log_summary.elapsed_seconds
    if elapsed_time is None:
        logger.error("无法解析作业运行时间")
        return

    para_eff = calculate_efficiency(
        hardware_config, parallelism_info, elapsed_time
    )
    if para_eff is None:
        logger.error("并行效率计算失败")
        return

    report_info = {
        "platform": hardware_config["hardware_name"],
        "node_num": script_info["nodes"],
        "app_name": script_info["job_name"],
        "core_num": parallelism_info["core_num"],
        "eff": f"{para_eff:.2f}%({hardware_config['compared_cores']} 节点)",
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    _attach_accelerator_summary(
        logger, job_dir, accelerator_config or {"accelerator_type": "none"},
        report_info,
    )

    logger.info(f"证书生成信息: {report_info}")
    try:
        from perfbench.report.certificate_generator import generate_certificate

        generate_certificate(report_info, job_dir)
    except ImportError:
        logger.warning("缺少 reportlab/pypdf，跳过 PDF 证书生成")


def _attach_accelerator_summary(logger, job_dir: str,
                                accelerator_config: dict,
                                report_info: dict) -> None:
    accel_monitor = get_accelerator_monitor(accelerator_config)
    log_subdir = accel_monitor.get_log_subdir()
    if not log_subdir or not os.path.isdir(os.path.join(job_dir, log_subdir)):
        return

    try:
        parsed_data = accel_monitor.parse_logs(job_dir)
        summary = accel_monitor.get_summary(parsed_data)
        if not summary:
            return

        logger.info(f"加速卡监控摘要: {summary}")
        for key, value in summary.items():
            report_info[f"accelerator_{key}"] = value
    except FileNotFoundError:
        logger.warning("未找到加速卡监控日志目录")
    except Exception as exc:
        logger.warning(f"解析加速卡监控日志失败: {exc}")
