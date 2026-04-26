#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PerfBench 包入口。

职责：
1. 解析 CLI 参数或交互式配置，产出统一评测请求。
2. 调用平台适配器执行作业，再生成报告。
"""

from datetime import datetime
import argparse
import os
import sys
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


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="PerfBench - 超算集群性能基准测试工具"
    )
    parser.add_argument("-init", action="store_true", help="初始化工具环境")
    parser.add_argument("-s", "--script", type=str, help="作业提交脚本路径")
    parser.add_argument("-t", "--interval", type=int, help="性能采集时间间隔（秒）")
    parser.add_argument("-o", "--output", type=str, help="输出目录路径")
    parser.add_argument("-v", action="store_true", help="运行工具适配性测试")
    parser.add_argument("--force", action="store_true",
                        help="跳过环境检测（仅用于调试）")
    parser.add_argument("--platform", choices=PLATFORM_CHOICES, default="slurm",
                        help="调度平台类型，默认 slurm")
    parser.add_argument("--accelerator", type=str, default=None,
                        choices=ACCELERATOR_CHOICES,
                        help="加速卡类型（覆盖 platform_config.json）")
    parser.add_argument("--accelerator-interval", type=int, default=None,
                        help="加速卡采样间隔（秒），默认使用全局 interval")
    parser.add_argument("--overhead", action="store_true",
                        help="开销测试模式：作业结束后额外抓取最终调度日志快照")
    parser.add_argument("--config", type=str, default=None,
                        help="测试配置文件路径（.yaml/.json），启用配置评测模式")
    parser.add_argument("--granularity", type=str, default=None,
                        choices=["board", "core"],
                        help="测试粒度等级: board（板卡级，默认）/ core（内部核级）")
    parser.add_argument("--init-config", action="store_true",
                        help="生成测试配置模板文件到当前目录")
    parser.add_argument("--version", action="version", version="%(prog)s 1.0.0")
    return parser


def main():
    parser = parse_arguments()
    args = parser.parse_args()
    logger = setup_logging()

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
            if not args.interval or not args.output:
                logger.error("请提供采集间隔(-t)和输出目录(-o)参数")
                sys.exit(1)

            progress = StepProgress(steps)
            progress.next()
            progress.next("监控脚本生成中")

            job_dir, script_info = _run_evaluation(
                script_path=args.script,
                interval=args.interval, # 登陆节点采样间隔
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

        _run_interactive_mode(steps, logger)

    except Exception as e:
        logger.error(f"执行过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def _run_interactive_mode(steps, logger):
    from perfbench.interactive import interactive_main

    config = interactive_main()
    if config is None:
        return

    if config["test_type"] == "application":
        script_path = config["script_path"]
    else:
        script_path = config["benchmark_script"]

    platform = config["platform"]
    interval = config["interval"]
    output_dir = config["output_dir"]

    progress = StepProgress(steps)
    progress.next()
    progress.next("监控脚本生成中")

    job_dir, script_info = _run_evaluation(
        script_path=script_path,
        interval=interval,
        output_dir=output_dir,
        platform=platform,
        progress=progress,
        logger=logger,
    )

    if config.get("nodes"):
        script_info["nodes"] = config["nodes"]

    _generate_report(logger, job_dir, script_info, interval, platform)
    progress.finish()


def _copy_config_template():
    """将内置配置模板复制到当前目录。"""
    import shutil

    template_dir = os.path.dirname(os.path.abspath(__file__))
    for ext in ("yaml", "json"):
        src = os.path.join(template_dir, f"test_config_template.{ext}")
        dst = os.path.join(os.getcwd(), f"test_config_template.{ext}")
        if os.path.isfile(src):
            shutil.copy2(src, dst)
            print(f"已生成: {dst}")
    print("请根据实际需求修改配置文件后，使用 --config 参数启动评测。")


def _run_config_mode(args, logger):
    """
    基于配置文件的评测模式入口。
    """
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
            logger.error(f"配置校验失败: {error}")
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
    logger.info(f"测试大纲已生成: {plan_path}")

    support_enabled = config.get("support", {}).get("enabled", False)
    if support_enabled:
        logger.info("模式: 支撑软件前后对比评测")
        orchestrator = BeforeAfterOrchestrator(config, adapter, output_dir)
    else:
        logger.info("模式: 多规模应用软件评测")
        orchestrator = MultiScaleOrchestrator(config, adapter, output_dir)

    result = orchestrator.run()

    md_path, json_path = generate_full_report(
        config, platform_config, result, output_dir,
        is_support=support_enabled,
    )
    logger.info(f"测试报告已生成: {md_path}, {json_path}")

    if "error" in result:
        logger.error(f"评测失败: {result['error']}")
        sys.exit(1)

    logger.info(f"评测完成，输出目录: {output_dir}")
    _log_config_mode_summary(logger, result, support_enabled)


def _log_config_mode_summary(logger, result: dict, support_enabled: bool):
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
    """
    通过平台适配器执行完整评测链路（提交 → 监控 → 等待）。
    """
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

    logger.info(f"PerfBench 流程已完成，输出目录: {job_dir}")
    progress.next("报告生成中")

    return job_dir, script_info


def _build_accelerator_config(platform_config: Optional[dict],
                              accelerator_override: Optional[str] = None,
                              accelerator_interval_override: Optional[int] = None
                              ) -> dict:
    """
    合并平台配置和 CLI 加速卡覆盖项。

    加速卡类型统一使用 --accelerator，采样间隔统一使用
    --accelerator-interval。
    """
    accel_config = dict(platform_config) if platform_config else {}
    if accelerator_override is not None:
        accel_config["accelerator_type"] = accelerator_override
    if accelerator_interval_override is not None:
        accel_config["accelerator_sampling_interval"] = (
            accelerator_interval_override
        )
    return accel_config


def _generate_report(logger, job_dir: str, script_info: dict,
                     interval: int, platform: str):
    """
    读取平台配置、计算并行度和效率，生成 PDF 证书。
    """
    platform_config = get_platform_config()
    if platform_config is None:
        logger.error("无法读取平台配置，报告生成失败")
        return

    parallelism_info = calculate_parallelism(
        platform_name=platform_config["platform_name"],
        node_num=script_info["nodes"],
    )
    if parallelism_info is None:
        logger.error("并行度计算失败，报告生成失败")
        return
    logger.info(f"计算得到的并行度: {parallelism_info}")

    log_parser = get_platform_adapter(platform).get_log_parser()
    log_summary = log_parser.parse_job_logs(job_dir, interval)
    elapsed_time = log_summary.elapsed_seconds
    if elapsed_time is None:
        logger.error("无法提取作业运行时间，报告生成失败")
        return

    para_eff = calculate_efficiency(
        platform_config, parallelism_info, elapsed_time
    )
    if para_eff is None:
        logger.error("效率计算失败，报告生成失败")
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

    logger.info(f"报告信息: {report_info}")
    try:
        from perfbench.report.certificate_generator import generate_certificate
        generate_certificate(report_info, job_dir)
    except ImportError:
        logger.warning("报告生成依赖（reportlab/pypdf）未安装，跳过 PDF 证书生成")


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

        logger.info(f"加速卡监控摘要: {summary}")
        for key, value in summary.items():
            report_info[f"accelerator_{key}"] = value
    except FileNotFoundError:
        logger.warning("加速卡日志目录存在但无日志文件，跳过加速卡分析")
    except Exception as e:
        logger.warning(f"加速卡日志解析失败: {e}")


if __name__ == "__main__":
    main()
