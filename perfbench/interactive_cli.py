#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Interactive command-line wizard for PerfBench evaluations."""

import os
import sys
from datetime import datetime
from types import SimpleNamespace
from typing import List, Optional

from perfbench.core.script_flow import run_script_flow
from perfbench.orchestrator.config_flow import run_config_flow
from perfbench.orchestrator.config_loader import load_test_config

try:
    import yaml

    HAS_YAML = True
except ImportError:
    HAS_YAML = False


PLATFORM_CHOICES = (
    ("slurm", "SLURM"),
    ("lsf", "LSF"),
    ("tianhe", "天河"),
)
ACCELERATOR_CHOICES = (
    ("none", "不启用加速卡监控"),
    ("dcu", "海光 DCU"),
    ("matrix", "Matrix 加速卡"),
)
MAIN_PATH_CHOICES = (
    ("application", "应用软件"),
    ("support", "支撑软件"),
)
GRANULARITY_CHOICES = (
    ("node", "节点级"),
    ("board", "卡级"),
    ("kernel", "kernel级"),
)
AGGREGATION_CHOICES = (
    ("mean", "平均值"),
    ("median", "中位数"),
    ("min", "最小值"),
)
SCALING_MODE_CHOICES = (
    ("strong", "强可扩展"),
    ("weak", "弱可扩展"),
)
PROFILE_RANK_SCOPE_CHOICES = (
    ("rank0", "仅 rank0"),
    ("all", "所有 rank"),
)
PROFILE_BACKEND_CHOICES = (
    ("hipprof", "hipprof（DTK/HIP trace，推荐当前环境）"),
    ("rocprofv3", "rocprofv3"),
)
SUPPORT_METRIC_TYPES = ("exec_perf", "io", "compile", "mixed_precision", "autotune")


def run_interactive_cli(logger) -> None:
    """Run the interactive PerfBench CLI and dispatch to existing flows."""
    _print_banner()
    main_path = _prompt_choice("请选择评测主路径", MAIN_PATH_CHOICES, default="application")
    granularity = _prompt_choice("请选择测试粒度", GRANULARITY_CHOICES, default="board")

    if granularity == "kernel":
        _run_kernel_profile_wizard(main_path, logger)
    else:
        _run_config_wizard(main_path, granularity, logger)


def _print_banner() -> None:
    print("")
    print("PerfBench 交互式评测入口")
    print("=" * 36)
    print("本入口仅负责收集参数，实际评测仍走既有 --config 或 --script 流程。")
    print("")


def _run_config_wizard(main_path: str, granularity: str, logger) -> None:
    print("")
    print("配置驱动评测")
    print("-" * 36)
    existing_config = _prompt_path(
        "已有 YAML 配置文件路径（回车则由向导生成临时配置）",
        required=False,
        must_exist=True,
    )
    output_dir = _prompt_path("输出目录", required=True, must_exist=False)
    interval = _prompt_int(
        "覆盖登录节点监控采样间隔（秒，回车使用配置文件或默认值）",
        default=None,
        minimum=1,
    )
    platform = _prompt_choice("调度平台", PLATFORM_CHOICES, default="slurm")
    accelerator = _prompt_choice("加速卡监控", ACCELERATOR_CHOICES, default="none")
    accelerator_interval = None
    if accelerator != "none":
        accelerator_interval = _prompt_int(
            "加速卡采样间隔（秒，回车使用登录节点采样间隔）",
            default=None,
            minimum=1,
        )

    if existing_config:
        config = load_test_config(existing_config)
        if config is None:
            sys.exit(1)
        _apply_interactive_overrides(config, main_path, granularity)
        _fill_missing_script_paths(config, main_path)
    else:
        config = _collect_generated_config(main_path, granularity, interval)

    effective_config = _write_effective_config(config, output_dir, main_path, granularity)
    args = SimpleNamespace(
        config=effective_config,
        output=output_dir,
        interval=interval,
        platform=platform,
        accelerator=None if accelerator == "none" else accelerator,
        accelerator_interval=accelerator_interval,
    )

    print("")
    print("即将启动配置驱动评测：")
    print(f"  主路径：{_label_for(MAIN_PATH_CHOICES, main_path)}")
    print(f"  测试粒度：{_label_for(GRANULARITY_CHOICES, granularity)}")
    print(f"  生效配置：{effective_config}")
    print("")
    run_config_flow(args, logger)


def _run_kernel_profile_wizard(main_path: str, logger) -> None:
    print("")
    print("Kernel 级观测")
    print("-" * 36)
    print("当前 kernel 级观测复用既有 --script --kernel-profile 流程，平台固定为 SLURM。")
    print("kernel 级路径不启动登录节点周期监控，也不启用加速卡时序监控。")
    output_dir = _prompt_path("输出目录", required=True, must_exist=False)
    interval = _prompt_int("性能采集时间间隔（秒）", default=60, minimum=1)
    profile_backend = _prompt_choice(
        "profile 后端",
        PROFILE_BACKEND_CHOICES,
        default="hipprof",
    )
    profile_counters = None
    if profile_backend == "rocprofv3":
        profile_counters = _prompt_text(
            "rocprofv3 counter 组（回车使用默认 SQ_WAVES,GRBM_GUI_ACTIVE）",
            default=None,
            required=False,
        )
    rank_scope = _prompt_choice(
        "profile MPI rank 范围",
        PROFILE_RANK_SCOPE_CHOICES,
        default="rank0",
    )

    if main_path == "support":
        before_script = _prompt_path(
            "before 脚本（无支撑软件版本）",
            required=True,
        )
        after_script = _prompt_path(
            "after 脚本（有支撑软件版本）",
            required=True,
        )
        runs = (
            ("before", before_script),
            ("after", after_script),
        )
    else:
        script = _prompt_path("作业脚本", required=True)
        runs = (("application", script),)

    for label, script in runs:
        run_output_dir = output_dir if len(runs) == 1 else os.path.join(output_dir, label)
        args = _build_kernel_args(
            script=script,
            output=run_output_dir,
            interval=interval,
            profile_backend=profile_backend,
            profile_counters=profile_counters,
            rank_scope=rank_scope,
        )
        print("")
        print(f"即将启动 kernel 级观测：{label}")
        print(f"  脚本：{script}")
        print(f"  输出目录：{run_output_dir}")
        run_script_flow(args, logger)


def _build_kernel_args(script: str, output: str, interval: int,
                       profile_backend: str,
                       profile_counters: Optional[str],
                       rank_scope: str):
    return SimpleNamespace(
        script=script,
        interval=interval,
        output=output,
        platform="slurm",
        accelerator=None,
        accelerator_interval=None,
        overhead=False,
        kernel_profile=True,
        profile_backend=profile_backend,
        profile_counters=profile_counters,
        profile_rank_scope=rank_scope,
        profile_output_subdir="kernel_profile",
    )


def _collect_generated_config(main_path: str, granularity: str,
                              interval: Optional[int]) -> dict:
    print("")
    print("生成临时 YAML 配置")
    print("-" * 36)
    repeat = _prompt_int("每个规模重复次数", default=1, minimum=1)
    aggregation = _prompt_choice("重复结果聚合方式", AGGREGATION_CHOICES, default="mean")
    scaling_mode = _prompt_choice("可扩展性模式", SCALING_MODE_CHOICES, default="strong")
    scales = _prompt_int_list("测试规模列表（节点数，逗号分隔）", default=[1, 2])

    scaling = {
        "mode": scaling_mode,
        "scales": scales,
        "datasets": [],
        "compute_ratios": [],
        "compute_ratio_method": "",
    }
    if scaling_mode == "weak":
        datasets = _prompt_csv("弱可扩展数据集路径列表（可留空）")
        ratios = _prompt_float_list("弱可扩展计算量倍率 F_s（可留空）")
        scaling["datasets"] = datasets
        scaling["compute_ratios"] = ratios

    config = {
        "global": {
            "granularity": granularity,
            "repeat": repeat,
            "aggregation": aggregation,
            "monitor_interval": interval or 60,
        },
        "scaling": scaling,
        "accuracy": {
            "enabled": False,
            "reference_file": "",
            "output_parser": "",
            "parser_options": {
                "column": 0,
                "delimiter": ",",
                "skip_header": True,
            },
            "metrics": ["absolute_error", "relative_error", "rmse"],
            "thresholds": {},
        },
        "scale_compliance": {
            "enabled": True,
            "active_util_threshold": 10.0,
            "scale_fraction_threshold": 0.8,
            "coverage_threshold": 0.9,
        },
        "support": {
            "enabled": main_path == "support",
            "before_script": "",
            "after_script": "",
            "metric_types": ["exec_perf"],
            "autotune_apps": [],
        },
        "job": {
            "script": "",
            "node_placeholder": "__NODES__",
            "dataset_placeholder": "__DATASET__",
        },
    }

    if main_path == "support":
        config["support"]["before_script"] = _prompt_path(
            "before 脚本（无支撑软件版本）",
            required=True,
        )
        config["support"]["after_script"] = _prompt_path(
            "after 脚本（有支撑软件版本）",
            required=True,
        )
        config["support"]["metric_types"] = _prompt_metric_types()
    else:
        config["support"]["enabled"] = False
        config["job"]["script"] = _prompt_path(
            "作业脚本",
            required=True,
        )

    return config


def _apply_interactive_overrides(config: dict, main_path: str,
                                 granularity: str) -> None:
    config.setdefault("global", {})["granularity"] = granularity
    support_cfg = config.setdefault("support", {})
    support_cfg["enabled"] = main_path == "support"


def _fill_missing_script_paths(config: dict, main_path: str) -> None:
    if main_path == "support":
        support_cfg = config.setdefault("support", {})
        if not support_cfg.get("before_script"):
            support_cfg["before_script"] = _prompt_path(
                "配置中缺少 before_script，请输入无支撑软件版本脚本",
                required=True,
            )
        if not support_cfg.get("after_script"):
            support_cfg["after_script"] = _prompt_path(
                "配置中缺少 after_script，请输入有支撑软件版本脚本",
                required=True,
            )
    else:
        job_cfg = config.setdefault("job", {})
        if not job_cfg.get("script"):
            job_cfg["script"] = _prompt_path(
                "配置中缺少 job.script，请输入应用作业脚本",
                required=True,
            )


def _write_effective_config(config: dict, output_dir: str, main_path: str,
                            granularity: str) -> str:
    if not HAS_YAML:
        print("需要 PyYAML 才能写入交互式生效配置，请先安装 pyyaml。")
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = "interactive_{0}_{1}_{2}.yaml".format(
        main_path,
        granularity,
        timestamp,
    )
    path = os.path.join(output_dir, filename)
    with open(path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(
            config,
            handle,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )
    return path


def _prompt_choice(prompt: str, choices, default: str):
    choice_map = {value: value for value, _label in choices}
    label_map = {_label.lower(): value for value, _label in choices}
    default_label = _label_for(choices, default)

    while True:
        print(prompt)
        for idx, (value, label) in enumerate(choices, start=1):
            marker = " [默认]" if value == default else ""
            print(f"  {idx}. {label}{marker}")
        raw = input(f"> ").strip()
        if not raw and default is not None:
            return default
        lowered = raw.lower()
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(choices):
                return choices[idx - 1][0]
        if lowered in choice_map:
            return choice_map[lowered]
        if lowered in label_map:
            return label_map[lowered]
        print(f"输入无效，请重新选择。默认值为：{default_label}")


def _prompt_text(prompt: str, default: Optional[str] = None,
                 required: bool = True) -> Optional[str]:
    while True:
        suffix = f" [{default}]" if default is not None else ""
        raw = input(f"{prompt}{suffix}: ").strip()
        if raw:
            return raw
        if default is not None:
            return default
        if not required:
            return None
        print("该项不能为空。")


def _prompt_path(prompt: str, required: bool = True,
                 must_exist: bool = True) -> Optional[str]:
    while True:
        value = _prompt_text(prompt, default=None, required=required)
        if value is None:
            return None
        path = os.path.abspath(os.path.expanduser(value))
        if must_exist and not os.path.exists(path):
            print(f"路径不存在：{path}")
            continue
        return path


def _prompt_int(prompt: str, default: Optional[int] = None,
                minimum: Optional[int] = None) -> Optional[int]:
    while True:
        suffix = f" [{default}]" if default is not None else ""
        raw = input(f"{prompt}{suffix}: ").strip()
        if not raw:
            return default
        try:
            value = int(raw)
        except ValueError:
            print("请输入整数。")
            continue
        if minimum is not None and value < minimum:
            print(f"请输入不小于 {minimum} 的整数。")
            continue
        return value


def _prompt_int_list(prompt: str, default: List[int]) -> List[int]:
    while True:
        raw = input(f"{prompt} [{','.join(str(x) for x in default)}]: ").strip()
        if not raw:
            return list(default)
        try:
            values = [int(item.strip()) for item in raw.split(",") if item.strip()]
        except ValueError:
            print("请输入逗号分隔的整数列表。")
            continue
        if len(values) < 2:
            print("至少需要两个规模（基准 + 目标）。")
            continue
        if any(value <= 0 for value in values):
            print("规模必须为正整数。")
            continue
        return values


def _prompt_float_list(prompt: str) -> List[float]:
    while True:
        raw = input(f"{prompt}: ").strip()
        if not raw:
            return []
        try:
            return [float(item.strip()) for item in raw.split(",") if item.strip()]
        except ValueError:
            print("请输入逗号分隔的数字列表。")


def _prompt_csv(prompt: str) -> List[str]:
    raw = input(f"{prompt}: ").strip()
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _prompt_metric_types() -> List[str]:
    raw = input(
        "支撑软件指标类型（逗号分隔，默认 exec_perf；可选 {0}）: ".format(
            ", ".join(SUPPORT_METRIC_TYPES)
        )
    ).strip()
    if not raw:
        return ["exec_perf"]

    values = [item.strip() for item in raw.split(",") if item.strip()]
    invalid = [item for item in values if item not in SUPPORT_METRIC_TYPES]
    if invalid:
        print("忽略不支持的指标类型：{0}".format(", ".join(invalid)))
    filtered = [item for item in values if item in SUPPORT_METRIC_TYPES]
    return filtered or ["exec_perf"]


def _label_for(choices, value: str) -> str:
    for item_value, label in choices:
        if item_value == value:
            return label
    return value
