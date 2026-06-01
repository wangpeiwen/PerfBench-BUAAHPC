#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PerfBench command-line entry point."""

import argparse
import sys

from perfbench.core.initializer import initialize_environment
from perfbench.interactive_cli import run_interactive_cli
from perfbench.core.script_flow import run_script_flow
from perfbench.core.validator import validate_environment
from perfbench.orchestrator.config_flow import (
    copy_config_template,
    run_config_flow,
)
from perfbench.utils.logger import setup_logging


PLATFORM_CHOICES = ("slurm", "lsf", "tianhe")
ACCELERATOR_CHOICES = ("dcu", "matrix", "none")
PROFILE_BACKEND_CHOICES = ("rocprofv3", "hipprof")
PROFILE_RANK_SCOPE_CHOICES = ("rank0", "all")


def parse_arguments() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="PerfBench - 超算集群性能基准测试工具"
    )
    parser.add_argument("-init", action="store_true", help="初始化工具运行环境")
    parser.add_argument("-s", "--script", type=str, help="作业提交脚本路径")
    parser.add_argument("-t", "--interval", type=int, help="性能采集时间间隔（秒）")
    parser.add_argument("-o", "--output", type=str, help="输出目录路径")
    parser.add_argument("-v", action="store_true", help="运行工具适配性测试")
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="启动命令行交互式评测入口",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="跳过环境检测（仅用于调试）",
    )
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
        help="测试配置文件路径（.yaml/.yml）",
    )
    parser.add_argument(
        "--init-config",
        action="store_true",
        help="复制测试配置模板到当前目录",
    )
    parser.add_argument(
        "--kernel-profile",
        action="store_true",
        help="启用 kernel ISA dump 和二次 profile 运行（仅 --script 模式）",
    )
    parser.add_argument(
        "--profile-backend",
        choices=PROFILE_BACKEND_CHOICES,
        default="rocprofv3",
        help="kernel profile 后端，默认 rocprofv3；可选 hipprof",
    )
    parser.add_argument(
        "--profile-counters",
        type=str,
        default=None,
        help="rocprofv3 counter 组，分号分隔多组，例如 'SQ_WAVES;GRBM_GUI_ACTIVE'；hipprof 后端忽略该参数",
    )
    parser.add_argument(
        "--profile-rank-scope",
        choices=PROFILE_RANK_SCOPE_CHOICES,
        default="rank0",
        help="profile 的 MPI rank 范围，默认 rank0",
    )
    parser.add_argument(
        "--profile-output-subdir",
        type=str,
        default="kernel_profile",
        help="kernel profile 输出子目录名，默认 kernel_profile",
    )
    parser.add_argument("--version", action="version", version="%(prog)s 1.0.0")
    return parser


def main() -> None:
    parser = parse_arguments()
    args = parser.parse_args()

    has_task = any([
        args.init,
        args.v,
        args.interactive,
        args.init_config,
        args.config,
        args.script,
    ])
    if not has_task:
        parser.print_help()
        return

    if not args.interactive:
        if args.script and (not args.interval or not args.output):
            parser.error("--script 模式必须同时指定 --interval 和 --output")
        if args.kernel_profile and not args.script:
            parser.error("--kernel-profile 仅支持 --script 模式")
        if args.kernel_profile and args.config:
            parser.error("--kernel-profile 暂不支持 --config 模式")
        if args.kernel_profile and args.platform != "slurm":
            parser.error("--kernel-profile 首版仅支持 --platform slurm")
        if args.kernel_profile and args.accelerator not in (None, "none"):
            parser.error("--kernel-profile 路径不启用 --accelerator 加速卡时序监控")
        if args.accelerator_interval is not None and args.accelerator is None:
            parser.error("--accelerator-interval 必须和 --accelerator 一起使用")

    logger = setup_logging()

    try:
        if args.interactive:
            run_interactive_cli(logger)
            return

        if args.init:
            initialize_environment(force=args.force)
            return

        if args.v:
            validate_environment(force=args.force)
            return

        if args.init_config:
            copy_config_template()
            return

        if args.config:
            run_config_flow(args, logger)
            return

        if args.script:
            run_script_flow(args, logger)
            return

    except Exception as exc:
        logger.error(f"PerfBench 执行失败: {exc}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
