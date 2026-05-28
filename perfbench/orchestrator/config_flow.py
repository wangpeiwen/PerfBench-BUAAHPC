#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Config-mode execution flow for PerfBench."""

import os
import shutil
import sys
from datetime import datetime
from typing import Optional

from perfbench.adapters.accelerator import get_accelerator_monitor
from perfbench.adapters.platform import get_platform_adapter
from perfbench.analysis import get_hardware_config
from perfbench.orchestrator.before_after import BeforeAfterOrchestrator
from perfbench.orchestrator.config_loader import (
    load_test_config,
    validate_test_config,
)
from perfbench.orchestrator.multi_scale import MultiScaleOrchestrator
from perfbench.report.full_report_generator import generate_full_report
from perfbench.report.test_plan_generator import generate_test_plan


def copy_config_template() -> None:
    """Copy the YAML test configuration template to the current directory."""
    template_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = os.path.join(template_dir, "test_config_template.yaml")
    dst = os.path.join(os.getcwd(), "test_config_template.yaml")

    if os.path.isfile(src):
        shutil.copy2(src, dst)
        print(f"已生成: {dst}")
    else:
        print("未找到配置模板文件")


def run_config_flow(args, logger) -> None:
    """Run the YAML config-driven evaluation flow."""
    config = load_test_config(args.config)
    if config is None:
        sys.exit(1)

    errors = validate_test_config(config)
    if errors:
        for error in errors:
            logger.error(f"配置文件校验失败: {error}")
        sys.exit(1)

    output_dir = args.output or os.path.join(
        os.getcwd(), f"perfbench_output_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    os.makedirs(output_dir, exist_ok=True)

    hardware_config = get_hardware_config()
    if hardware_config:
        config["hardware_name"] = hardware_config.get("hardware_name", "")

    accelerator_config = _build_accelerator_config(
        accelerator_type=args.accelerator,
        accelerator_interval=args.accelerator_interval,
    )
    report_hardware_config = _build_report_hardware_config(
        hardware_config, accelerator_config
    )
    accel_monitor = get_accelerator_monitor(accelerator_config)
    adapter = get_platform_adapter(
        args.platform, accelerator_monitor=accel_monitor
    )

    plan_path = generate_test_plan(config, report_hardware_config, output_dir)
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
        config, report_hardware_config, result, output_dir,
        is_support=support_enabled,
    )
    logger.info(f"完整报告已生成: {md_path}, {json_path}")

    if "error" in result:
        logger.error(f"评测失败: {result['error']}")
        sys.exit(1)

    logger.info(f"评测输出目录: {output_dir}")
    _log_config_mode_summary(logger, result, support_enabled)


def _build_accelerator_config(accelerator_type: Optional[str] = None,
                              accelerator_interval: Optional[int] = None
                              ) -> dict:
    accelerator_config = {"accelerator_type": accelerator_type or "none"}
    if accelerator_interval is not None:
        accelerator_config["accelerator_sampling_interval"] = accelerator_interval
    return accelerator_config


def _build_report_hardware_config(hardware_config: Optional[dict],
                                  accelerator_config: dict) -> Optional[dict]:
    if hardware_config is None:
        return None

    report_config = dict(hardware_config)
    report_config["accelerator_type"] = accelerator_config.get(
        "accelerator_type", "none"
    )
    return report_config


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
