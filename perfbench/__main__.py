#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PerfBench command-line entry point."""

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
from perfbench.core.script_processor import run_evaluation
from perfbench.core.validator import validate_environment
from perfbench.utils.logger import setup_logging
from perfbench.utils.progress_bar import StepProgress


PLATFORM_CHOICES = ("slurm", "lsf", "tianhe")
ACCELERATOR_CHOICES = ("dcu", "matrix", "none")


def parse_arguments() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="PerfBench - HPC performance benchmark tool"
    )
    parser.add_argument("-init", action="store_true", help="initialize runtime environment")
    parser.add_argument("-s", "--script", type=str, help="job submission script path")
    parser.add_argument("-t", "--interval", type=int, help="monitoring interval in seconds")
    parser.add_argument("-o", "--output", type=str, help="output directory")
    parser.add_argument("-v", action="store_true", help="validate runtime environment")
    parser.add_argument("--force", action="store_true", help="skip environment checks for debugging")
    parser.add_argument(
        "--platform",
        choices=PLATFORM_CHOICES,
        default="slurm",
        help="scheduler platform, default: slurm",
    )
    parser.add_argument(
        "--accelerator",
        type=str,
        default=None,
        choices=ACCELERATOR_CHOICES,
        help="accelerator type, overrides platform_config.json",
    )
    parser.add_argument(
        "--accelerator-interval",
        type=int,
        default=None,
        help="accelerator sampling interval in seconds, defaults to --interval",
    )
    parser.add_argument(
        "--overhead",
        action="store_true",
        help="capture a final scheduler log snapshot after the job ends",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="test configuration file path (.yaml/.json)",
    )
    parser.add_argument(
        "--granularity",
        type=str,
        default=None,
        choices=["board", "core"],
        help="test granularity: board or core",
    )
    parser.add_argument(
        "--init-config",
        action="store_true",
        help="copy test configuration templates to the current directory",
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
        parser.error("--script mode requires both --interval and --output")

    logger = setup_logging()

    steps = [
        "Read job script",
        "Prepare instrumented script",
        "Submit job",
        "Start monitoring",
        "Wait for job",
        "Generate report",
        "Finish report",
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
            progress.next("Prepare instrumented script")

            job_dir, script_info = _run_evaluation(
                script_path=args.script,
                interval=args.interval,
                output_dir=args.output,
                platform=args.platform,
                progress=progress,
                logger=logger,
                accelerator_override=args.accelerator,
                accelerator_interval_override=args.accelerator_interval,
                overhead_mode=args.overhead,
            )
            _generate_report(
                logger, job_dir, script_info, args.interval, args.platform
            )
            progress.finish()
            return

    except Exception as exc:
        logger.error(f"PerfBench failed: {exc}")
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
        print(f"generated: {path}")
    if not copied:
        print("no config templates found")


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
            logger.error(f"invalid config: {error}")
        sys.exit(1)

    output_dir = args.output or os.path.join(
        os.getcwd(), f"perfbench_output_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    os.makedirs(output_dir, exist_ok=True)

    platform_config = get_platform_config()
    accel_config = _build_accelerator_config(
        platform_config,
        accelerator_override=args.accelerator,
        accelerator_interval_override=args.accelerator_interval,
    )
    accel_monitor = get_accelerator_monitor(accel_config)
    adapter = get_platform_adapter(
        args.platform, accelerator_monitor=accel_monitor
    )

    plan_path = generate_test_plan(config, platform_config, output_dir)
    logger.info(f"test plan generated: {plan_path}")

    support_enabled = config.get("support", {}).get("enabled", False)
    if support_enabled:
        logger.info("running before/after support-software evaluation")
        orchestrator = BeforeAfterOrchestrator(config, adapter, output_dir)
    else:
        logger.info("running multi-scale application evaluation")
        orchestrator = MultiScaleOrchestrator(config, adapter, output_dir)

    result = orchestrator.run()

    md_path, json_path = generate_full_report(
        config, platform_config, result, output_dir,
        is_support=support_enabled,
    )
    logger.info(f"full report generated: {md_path}, {json_path}")

    if "error" in result:
        logger.error(f"evaluation failed: {result['error']}")
        sys.exit(1)

    logger.info(f"evaluation output directory: {output_dir}")
    _log_config_mode_summary(logger, result, support_enabled)


def _log_config_mode_summary(logger, result: dict, support_enabled: bool) -> None:
    if support_enabled:
        for metric, values in result.get("improvements", {}).items():
            logger.info(f"  {metric}: {values}")
        return

    for entry in result.get("scalability_report", []):
        logger.info(
            f"  cores={entry.get('cores')}, "
            f"speedup={entry.get('speedup', 0):.2f}, "
            f"efficiency={entry.get('efficiency', 0):.2f}%"
        )


def _run_evaluation(script_path: str, interval: int, output_dir: str,
                    platform: str, progress, logger,
                    accelerator_override: Optional[str] = None,
                    accelerator_interval_override: Optional[int] = None,
                    overhead_mode: bool = False):
    platform_config = get_platform_config()
    accel_config = _build_accelerator_config(
        platform_config,
        accelerator_override=accelerator_override,
        accelerator_interval_override=accelerator_interval_override,
    )

    accel_monitor = get_accelerator_monitor(accel_config)
    adapter = get_platform_adapter(platform, accelerator_monitor=accel_monitor)
    job_dir, script_info = run_evaluation(
        script_path, interval, output_dir, adapter, progress,
        capture_final_logs=overhead_mode,
    )

    logger.info(f"PerfBench evaluation output directory: {job_dir}")
    progress.next("Generate report")

    return job_dir, script_info


def _build_accelerator_config(platform_config: Optional[dict],
                              accelerator_override: Optional[str] = None,
                              accelerator_interval_override: Optional[int] = None
                              ) -> dict:
    accel_config = dict(platform_config) if platform_config else {}
    if accelerator_override is not None:
        accel_config["accelerator_type"] = accelerator_override
    if accelerator_interval_override is not None:
        accel_config["accelerator_sampling_interval"] = (
            accelerator_interval_override
        )
    return accel_config


def _generate_report(logger, job_dir: str, script_info: dict,
                     interval: int, platform: str) -> None:
    platform_config = get_platform_config()
    if platform_config is None:
        logger.error("failed to read platform configuration")
        return

    parallelism_info = calculate_parallelism(
        platform_name=platform_config["platform_name"],
        node_num=script_info["nodes"],
    )
    if parallelism_info is None:
        logger.error("failed to calculate parallelism")
        return
    logger.info(f"parallelism: {parallelism_info}")

    log_parser = get_platform_adapter(platform).get_log_parser()
    log_summary = log_parser.parse_job_logs(job_dir, interval)
    elapsed_time = log_summary.elapsed_seconds
    if elapsed_time is None:
        logger.error("failed to parse elapsed job time")
        return

    para_eff = calculate_efficiency(
        platform_config, parallelism_info, elapsed_time
    )
    if para_eff is None:
        logger.error("failed to calculate parallel efficiency")
        return

    report_info = {
        "platform": platform_config["platform_name"],
        "node_num": script_info["nodes"],
        "app_name": script_info["job_name"],
        "core_num": parallelism_info["core_num"],
        "eff": f"{para_eff:.2f}%({platform_config['compared_cores']} Nodes)",
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    _attach_accelerator_summary(logger, job_dir, platform_config, report_info)

    logger.info(f"certificate data: {report_info}")
    try:
        from perfbench.report.certificate_generator import generate_certificate

        generate_certificate(report_info, job_dir)
    except ImportError:
        logger.warning("reportlab/pypdf is missing; PDF certificate was skipped")


def _attach_accelerator_summary(logger, job_dir: str,
                                platform_config: dict,
                                report_info: dict) -> None:
    accel_monitor = get_accelerator_monitor(platform_config)
    log_subdir = accel_monitor.get_log_subdir()
    if not log_subdir or not os.path.isdir(os.path.join(job_dir, log_subdir)):
        return

    try:
        parsed_data = accel_monitor.parse_logs(job_dir)
        summary = accel_monitor.get_summary(parsed_data)
        if not summary:
            return

        logger.info(f"accelerator summary: {summary}")
        for key, value in summary.items():
            report_info[f"accelerator_{key}"] = value
    except FileNotFoundError:
        logger.warning("accelerator log directory was not found")
    except Exception as exc:
        logger.warning(f"failed to parse accelerator logs: {exc}")


if __name__ == "__main__":
    main()
