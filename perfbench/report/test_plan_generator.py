#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试大纲自动生成器。

根据用户配置文件和平台信息，自动生成符合国标规范（§3.1）的测试大纲文档。
输出格式：Markdown（可直接转 Word/PDF）。

规范要求的测试大纲内容：
- 任务书指标
- 测试环境（平台、节点数、处理器型号、加速卡）
- 指标的拟测试用例和测试方法
- 测试步骤及具体测试命令
- 特别明确：应用用例数量和类型、重复测试次数、指标计算方式
"""

import os
from datetime import datetime
from typing import Optional


GRANULARITY_LABELS = {
    "node": "节点级",
    "board": "卡级/板卡级",
    "core": "内部核级",
}


def generate_test_plan(config: dict, hardware_config: Optional[dict],
                       output_dir: str) -> str:
    """
    从测试配置和硬件配置生成测试大纲 Markdown 文件。

    Args:
        config: 用户测试配置（从 test_config_template.yaml 加载）
        hardware_config: 硬件配置字典（hardware_config.json）
        output_dir: 输出目录

    Returns:
        str: 生成的测试大纲文件路径
    """
    global_cfg = config.get("global", {})
    scaling_cfg = config.get("scaling", {})
    accuracy_cfg = config.get("accuracy", {})
    support_cfg = config.get("support", {})
    job_cfg = config.get("job", {})

    granularity = global_cfg.get("granularity", "board")
    repeat = global_cfg.get("repeat", 3)
    aggregation = global_cfg.get("aggregation", "mean")

    is_support = support_cfg.get("enabled", False)
    mode_name = "支撑软件评测" if is_support else "应用软件评测"

    lines = []
    lines.append(f"# 测试大纲 — {mode_name}")
    lines.append("")
    lines.append(f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"> 生成工具：PerfBench-BUAAHPC v1.0")
    lines.append("")

    # ── 1. 任务书指标 ──
    lines.append("## 1. 任务书指标")
    lines.append("")
    if is_support:
        metric_types = support_cfg.get("metric_types", [])
        lines.append("| 指标类别 | 说明 |")
        lines.append("|----------|------|")
        _metric_desc = {
            "exec_perf": "执行性能提升率",
            "io": "I/O 性能提升率",
            "compile": "编译优化性能提升率",
            "mixed_precision": "混合精度性能提升率",
            "autotune": "自动调优平均提升率",
        }
        for mt in metric_types:
            lines.append(f"| {mt} | {_metric_desc.get(mt, mt)} |")
    else:
        lines.append("| 指标 | 说明 |")
        lines.append("|------|------|")
        lines.append("| 并行规模 | 处理器核数认定（板卡级/内部核级） |")
        lines.append("| 并行效率 | E = (T_M × M) / (T_N × N) × 100% |")
        if scaling_cfg.get("mode") == "strong":
            lines.append("| 强可扩展性 | 固定问题规模，增加核数 |")
        elif scaling_cfg.get("mode") == "weak":
            lines.append("| 弱可扩展性 | 问题规模随核数等比增长 |")
        else:
            lines.append("| 可扩展性 | 强/弱可扩展并行效率 |")
        if accuracy_cfg.get("enabled", False):
            lines.append("| 数值模拟精度 | 绝对误差/相对误差/RMSE |")
    lines.append("")

    # ── 2. 测试环境 ──
    lines.append("## 2. 测试环境")
    lines.append("")
    hardware_name = "未指定"
    processor = "未指定"
    accel_type = "无"
    if hardware_config:
        hardware_name = hardware_config.get("hardware_name", hardware_name)
        processor = hardware_config.get("processor_name", processor)
        accel_type = hardware_config.get("accelerator_type", "none")
    lines.append(f"- 硬件名称：{hardware_name}")
    lines.append(f"- 处理器型号：{processor}")
    lines.append(f"- 加速卡类型：{accel_type}")
    lines.append(
        f"- 测试粒度：{granularity}（{_granularity_label(granularity)}）"
    )
    scales = scaling_cfg.get("scales", [])
    if scales:
        lines.append(f"- 测试规模（节点数）：{scales}")
    lines.append("")

    # ── 3. 测试用例与测试方法 ──
    lines.append("## 3. 测试用例与测试方法")
    lines.append("")
    lines.append(f"### 3.1 应用用例")
    lines.append("")
    script = job_cfg.get("script", "用户提供")
    lines.append(f"- 作业脚本：`{script}`")
    datasets = scaling_cfg.get("datasets", [])
    if datasets:
        lines.append(f"- 数据集：{len(datasets)} 个")
        for ds in datasets:
            lines.append(f"  - `{ds}`")
    lines.append("")

    lines.append(f"### 3.2 测试方法")
    lines.append("")
    lines.append(f"- 重复测试次数：**{repeat}** 次")
    lines.append(f"- 指标计算方式：取 {repeat} 次结果的 **{aggregation}** 值")
    if is_support:
        lines.append(f"- 对比方式：同一应用的两个版本（有/无支撑软件）分别评测")
        lines.append(f"- before 脚本：`{support_cfg.get('before_script', '用户提供')}`")
        lines.append(f"- after 脚本：`{support_cfg.get('after_script', '用户提供')}`")
    else:
        lines.append(f"- 可扩展性模式：{scaling_cfg.get('mode', 'strong')}")
        if scaling_cfg.get("mode") == "weak":
            ratios = scaling_cfg.get("compute_ratios", [])
            lines.append(f"- 弱可扩展性计算量比 F_s：{ratios}")
    lines.append("")

    # ── 4. 测试步骤及具体命令 ──
    lines.append("## 4. 测试步骤及具体命令")
    lines.append("")
    lines.append("### 步骤 1：环境验证")
    lines.append("```bash")
    lines.append("./perfbench.py -v")
    lines.append("```")
    lines.append("")
    lines.append("### 步骤 2：启动评测")
    lines.append("```bash")
    cmd_parts = ["./perfbench.py --config <config_file>"]
    cmd_parts.append("-o <output_dir>")
    lines.append(" ".join(cmd_parts))
    lines.append("```")
    lines.append("")
    lines.append("### 步骤 3：检查输出")
    lines.append("")
    lines.append("评测完成后检查输出目录中的以下文件：")
    lines.append("- `test_plan.md` — 本测试大纲")
    lines.append("- `test_report.md` — 完整测试报告")
    lines.append("- `test_report.json` — 结构化测试结果")
    lines.append("")

    # ── 5. 特别说明 ──
    lines.append("## 5. 特别说明")
    lines.append("")
    lines.append(f"1. 应用用例数量：{max(1, len(datasets))} 个")
    lines.append(f"2. 每项指标重复测试次数：{repeat} 次")
    lines.append(f"3. 最终指标计算方式：{aggregation}")
    lines.append("")
    lines.append("---")
    lines.append("*本测试大纲由 PerfBench 自动生成，符合《高性能应用评测指标体系与规范(十四五试行)V1.0》§3.1 要求。*")

    # 写入文件
    os.makedirs(output_dir, exist_ok=True)
    plan_path = os.path.join(output_dir, "test_plan.md")
    with open(plan_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    return plan_path


def _granularity_label(granularity: str) -> str:
    return GRANULARITY_LABELS.get(granularity, granularity)
