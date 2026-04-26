#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PerfBench 命令行入口。"""

import argparse
import os
import sys
from datetime import datetime
from typing import Optional

from perfbench.adapters.accelerator import get_accelerator_monitor
from perfbench.adapters.platform import get_platform_adapter
from perfbench.analysis import (
    calculate_efficiency,
    calculate_parallelism,
    get_platform_config,
)
from perfbench.core.initializer import initialize_environment
from perfbench.core.job_runner import run_evaluation
from perfbench.core.validator import validate_environment
from perfbench.utils.logger import setup_logging
from perfbench.utils.progress_bar import StepProgress


PLATFORM_CHOICES = ("slurm", "lsf", "tianhe")
ACCELERATOR_CHOICES = ("dcu", "matrix", "none")


def parse_arguments() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="PerfBench - 超算集群性能基准测试工具"
    )
    parser.add_argument("-init", action="store_true", help="初始化工具运行环境")
    parser.add_argument("-s", "--script", type=str, help="作业提交脚本路径")
    parser.add_argument("-t", "--interval", type=int, help="性能采集时间间隔（秒）")
    parser.add_argument("-o", "--output", type=str, help="输出目录路径")
    parser.add_argument("-v", action="store_true", help="运行工具适配性测试")
    parser.add_argument("--force", action="store_true",
                        help="跳过环境检测（仅用于调试）")
    parser.add_argument(
        "--platform",
        choices=PLATFORM_CHOICES,
        default="slurm",
        help="调度平台类型，默认 slurm",
    )
    parser.add_argument(
        "--accelerator",
        type=str,
        default=None,
        choices=ACCELERATOR_CHOICES,
        help="加速卡类型（仅在显式指定时启用采样）",
    )
    parser.add_argument(
        "--accelerator-interval",
        type=int,
        default=None,
        help="加速卡采样间隔（秒），默认使用全局 interval",
    )
    parser.add_argument(
        "--overhead",
        action="store_true",
        help="开销测试模式：作业结束后额外抓取最终调度日志快照",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="测试配置文件路径（.yaml/.json）",
    )
    parser.add_argument(
        "--granularity",
        type=str,
        default=None,
        choices=["board", "core"],
        help="测试粒度等级：board（板卡级）/ core（内部核级）",
    )
    parser.add_argument(
        "--init-config",
        action="store_true",
        help="复制测试配置模板到当前目录",
    )
    parser.add_argument("--version", action="version", version="%(prog)s 1.0.0")
    return parser


def main() -> None:
    parser = parse_arguments()
    args = parser.parse_args()

    has_task = any([
        args.init,
        args.v,
        args.init_config,
        args.config,
        args.script,
    ])
    if not has_task:
        parser.print_help()
        return

    if args.script and (not args.interval or not args.output):
        parser.error("--script 模式必须同时指定 --interval 和 --output")
    if args.accelerator_interval is not None and args.accelerator is None:
        parser.error("--accelerator-interval 必须和 --accelerator 一起使用")

    logger = setup_logging()

    steps = [
        "读取作业提交脚本",
        "生成监控脚本",
        "提交作业",
        "启动监控",
        "等待作业结束",
        "生成报告",
        "报告生成完成",
    ]

    try:
        if args.init:
            initialize_environment(force=args.force)
            return

        if args.v:
            validate_environment(force=args.force)
            return

        if args.init_config:
            _copy_config_template()
            return

        if args.config:
            _run_config_mode(args, logger)
            return

        if args.script:
            progress = StepProgress(steps)
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
            return

    except Exception as exc:
        logger.error(f"PerfBench 执行失败: {exc}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


def _copy_config_template() -> None:
    import shutil

    template_dir = os.path.dirname(os.path.abspath(__file__))
    copied = []
    for ext in ("yaml", "json"):
        src = os.path.join(template_dir, f"test_config_template.{ext}")
        dst = os.path.join(os.getcwd(), f"test_config_template.{ext}")
        if os.path.isfile(src):
            shutil.copy2(src, dst)
            copied.append(dst)

    for path in copied:
        print(f"已生成: {path}")
    if not copied:
        print("未找到配置模板文件")


def _run_config_mode(args, logger) -> None:
    from perfbench.orchestrator.before_after import BeforeAfterOrchestrator
    from perfbench.orchestrator.config_loader import (
        load_test_config,
        validate_test_config,
    )
    from perfbench.orchestrator.multi_scale import MultiScaleOrchestrator
    from perfbench.report.full_report_generator import generate_full_report
    from perfbench.report.test_plan_generator import generate_test_plan

    config = load_test_config(args.config)
    if config is None:
        sys.exit(1)

    if args.granularity:
        config.setdefault("global", {})["granularity"] = args.granularity

    errors = validate_test_config(config)
    if errors:
        for error in errors:
            logger.error(f"配置文件校验失败: {error}")
        sys.exit(1)

    output_dir = args.output or os.path.join(
        os.getcwd(), f"perfbench_output_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    os.makedirs(output_dir, exist_ok=True)

    platform_config = get_platform_config()
    accelerator_config = _build_accelerator_config(
        accelerator_type=args.accelerator,
        accelerator_interval=args.accelerator_interval,
    )
    report_platform_config = _build_report_platform_config(
        platform_config, accelerator_config
    )
    accel_monitor = get_accelerator_monitor(accelerator_config)
    adapter = get_platform_adapter(
        args.platform, accelerator_monitor=accel_monitor
    )

    plan_path = generate_test_plan(config, report_platform_config, output_dir)
    logger.info(f"测试计划已生成: {plan_path}")

    support_enabled = config.get("support", {}).get("enabled", False)
    if support_enabled:
        logger.info("评测模式：支撑软件前后对比评测")
        orchestrator = BeforeAfterOrchestrator(config, adapter, output_dir)
    else:
        logger.info("评测模式：应用软件多尺度评测")
        orchestrator = MultiScaleOrchestrator(config, adapter, output_dir)

    result = orchestrator.run()

    md_path, json_path = generate_full_report(
        config, report_platform_config, result, output_dir,
        is_support=support_enabled,
    )
    logger.info(f"完整报告已生成: {md_path}, {json_path}")

    if "error" in result:
        logger.error(f"评测失败: {result['error']}")
        sys.exit(1)

    logger.info(f"评测输出目录: {output_dir}")
    _log_config_mode_summary(logger, result, support_enabled)


def _log_config_mode_summary(logger, result: dict, support_enabled: bool) -> None:
    if support_enabled:
        for metric, values in result.get("improvements", {}).items():
            logger.info(f"  {metric}: {values}")
        return

    for entry in result.get("scalability_report", []):
        logger.info(
            f"  核数={entry.get('cores')}, "
            f"加速比={entry.get('speedup', 0):.2f}, "
            f"并行效率={entry.get('efficiency', 0):.2f}%"
        )


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
    job_dir, script_info = run_evaluation(
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


def _build_report_platform_config(platform_config: Optional[dict],
                                  accelerator_config: dict) -> Optional[dict]:
    if platform_config is None:
        return None

    report_config = dict(platform_config)
    report_config["accelerator_type"] = accelerator_config.get(
        "accelerator_type", "none"
    )
    return report_config


def _generate_report(logger, job_dir: str, script_info: dict,
                     interval: int, platform: str,
                     accelerator_config: Optional[dict] = None) -> None:
    platform_config = get_platform_config()
    if platform_config is None:
        logger.error("读取平台配置失败")
        return

    parallelism_info = calculate_parallelism(
        platform_name=platform_config["platform_name"],
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
        platform_config, parallelism_info, elapsed_time
    )
    if para_eff is None:
        logger.error("并行效率计算失败")
        return

    report_info = {
        "platform": platform_config["platform_name"],
        "node_num": script_info["nodes"],
        "app_name": script_info["job_name"],
        "core_num": parallelism_info["core_num"],
        "eff": f"{para_eff:.2f}%({platform_config['compared_cores']} 节点)",
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


if __name__ == "__main__":
    main()
