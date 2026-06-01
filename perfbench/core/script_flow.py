#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Script-mode execution flow for PerfBench."""

import json
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
from perfbench.profile import KernelProfileConfig, get_profile_backend
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
    profile_backend = _build_profile_backend(args, logger)

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
        profile_backend=profile_backend,
    )
    _generate_report(
        logger, job_dir, script_info, args.interval, args.platform,
        _build_accelerator_config(
            accelerator_type=args.accelerator,
            accelerator_interval=args.accelerator_interval,
        ),
    )
    if profile_backend is not None:
        _run_kernel_profile(args, logger, job_dir, profile_backend)
    progress.finish()


def _run_evaluation(script_path: str, interval: int, output_dir: str,
                    platform: str, progress, logger,
                    accelerator_type: Optional[str] = None,
                    accelerator_interval: Optional[int] = None,
                    overhead_mode: bool = False,
                    profile_backend=None):
    accelerator_config = _build_accelerator_config(
        accelerator_type=accelerator_type,
        accelerator_interval=accelerator_interval,
    )

    accel_monitor = get_accelerator_monitor(accelerator_config)
    adapter = get_platform_adapter(platform, accelerator_monitor=accel_monitor)
    script_transformer = None
    if profile_backend is not None:
        script_transformer = (
            lambda path, info, sample_interval, job_dir:
            profile_backend.inject_formal_run(path, job_dir)
        )

    job_dir, script_info = run_job_evaluation(
        script_path, interval, output_dir, adapter, progress,
        capture_final_logs=overhead_mode or profile_backend is not None,
        script_transformer=script_transformer,
    )

    logger.info(f"PerfBench 评测输出目录: {job_dir}")
    progress.next("生成报告")

    return job_dir, script_info


def _build_profile_backend(args, logger):
    if not getattr(args, "kernel_profile", False):
        return None

    profile_config = KernelProfileConfig(
        backend=args.profile_backend,
        counters=args.profile_counters,
        rank_scope=args.profile_rank_scope,
        output_subdir=args.profile_output_subdir,
    )
    backend = get_profile_backend(profile_config)
    backend.preflight(args.script)
    logger.info(
        f"kernel profile 已启用: backend={profile_config.backend}, "
        f"rank_scope={profile_config.rank_scope}, "
        f"output_subdir={profile_config.output_subdir}"
    )
    return backend


def _run_kernel_profile(args, logger, job_dir: str, profile_backend) -> None:
    profile_dir = os.path.join(job_dir, args.profile_output_subdir)
    profile_run_dir = os.path.join(profile_dir, "profile_run")
    os.makedirs(profile_run_dir, exist_ok=True)

    logger.info(f"开始二次 profile 运行，输出目录: {profile_dir}")
    profile_script = profile_backend.inject_profile_run(args.script, profile_dir)

    adapter = get_platform_adapter(
        args.platform,
        accelerator_monitor=get_accelerator_monitor({"accelerator_type": "none"}),
    )
    script_info = adapter.parse_script(profile_script)
    if script_info is None:
        raise RuntimeError(f"无法解析 profile 脚本: {profile_script}")

    prepared_script = adapter.prepare_script(
        profile_script, script_info, args.interval, profile_run_dir
    )
    jobid = adapter.submit_job(prepared_script)
    logger.info(f"profile 作业已提交, JobID={jobid}")
    adapter.start_monitoring(jobid, args.interval, profile_run_dir)
    final_state = adapter.wait_for_job(jobid)
    adapter.capture_final_logs(jobid, profile_run_dir)

    profile_log_summary = _safe_parse_job_logs(
        adapter, profile_run_dir, args.interval, logger
    )
    formal_log_summary = _safe_parse_job_logs(
        get_platform_adapter(args.platform), job_dir, args.interval, logger
    )

    summary = profile_backend.parse_outputs(job_dir, profile_dir)
    summary["formal_run"] = {
        "output_dir": job_dir,
        "elapsed_seconds": (
            formal_log_summary.elapsed_seconds if formal_log_summary else None
        ),
        "state": formal_log_summary.final_state if formal_log_summary else None,
    }
    summary["profile_run"] = {
        "job_id": jobid,
        "state": final_state,
        "output_dir": profile_run_dir,
        "elapsed_seconds": (
            profile_log_summary.elapsed_seconds if profile_log_summary else None
        ),
        "note": "profile run elapsed is not used for formal performance metrics",
    }

    summary_path = os.path.join(profile_dir, "kernel_profile_summary.json")
    with open(summary_path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
    logger.info(f"kernel profile 摘要已生成: {summary_path}")


def _safe_parse_job_logs(adapter, output_dir: str, interval: int, logger):
    try:
        return adapter.get_log_parser().parse_job_logs(output_dir, interval)
    except Exception as exc:
        logger.warning(f"解析调度日志失败: {output_dir}: {exc}")
        return None


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
