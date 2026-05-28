#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
完整评测报告生成器。

从编排器输出的结果数据生成符合国标规范（§3.2）的测试报告。
输出格式：Markdown + JSON。

规范要求的测试报告内容：
- 测试方法、测试环境、测试步骤
- 各项性能和功能指标的测试内容和测试结果
- 附件清单（输入数据、输出结果、作业脚本）
"""

import os
import json
from datetime import datetime
from typing import Optional


def generate_full_report(config: dict, hardware_config: Optional[dict],
                         result: dict, output_dir: str,
                         is_support: bool = False) -> tuple:
    """
    从编排器结果生成完整评测报告。

    Args:
        config: 用户测试配置
        hardware_config: 硬件配置字典
        result: 编排器 run() 返回的结果字典
        output_dir: 输出目录
        is_support: 是否为支撑软件评测模式

    Returns:
        tuple: (markdown_path, json_path)
    """
    global_cfg = config.get("global", {})
    scaling_cfg = config.get("scaling", {})
    support_cfg = config.get("support", {})
    job_cfg = config.get("job", {})

    granularity = global_cfg.get("granularity", "board")
    repeat = global_cfg.get("repeat", 3)
    aggregation = global_cfg.get("aggregation", "mean")
    mode_name = "支撑软件评测" if is_support else "应用软件评测"

    lines = []
    lines.append(f"# 测试报告 — {mode_name}")
    lines.append("")
    lines.append(f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"> 生成工具：PerfBench-BUAAHPC v1.0")
    lines.append("")

    # ── 1. 测试环境 ──
    lines.append("## 1. 测试环境")
    lines.append("")
    hardware_name = "未指定"
    processor = "未指定"
    accel_type = "无"
    if hardware_config:
        hardware_name = hardware_config.get("hardware_name", hardware_name)
        processor = hardware_config.get("processor_name", processor)
        accel_type = hardware_config.get("accelerator_type", "none")
    lines.append(f"| 项目 | 内容 |")
    lines.append(f"|------|------|")
    lines.append(f"| 硬件 | {hardware_name} |")
    lines.append(f"| 处理器 | {processor} |")
    lines.append(f"| 加速卡 | {accel_type} |")
    lines.append(f"| 测试粒度 | {granularity} |")
    lines.append(f"| 重复次数 | {repeat} |")
    lines.append(f"| 聚合方式 | {aggregation} |")
    lines.append("")

    # ── 2. 测试方法 ──
    lines.append("## 2. 测试方法")
    lines.append("")
    if is_support:
        lines.append("采用同一应用的两个版本（有/无支撑软件）分别在相同规模下运行，")
        lines.append("对比执行时间和 I/O 性能，计算性能提升率。")
        lines.append("")
        lines.append(f"- before 脚本：`{support_cfg.get('before_script', 'N/A')}`")
        lines.append(f"- after 脚本：`{support_cfg.get('after_script', 'N/A')}`")
    else:
        mode = scaling_cfg.get("mode", "strong")
        lines.append(f"- 可扩展性模式：{mode}")
        lines.append(f"- 测试规模：{scaling_cfg.get('scales', [])}")
        lines.append(f"- 作业脚本：`{job_cfg.get('script', 'N/A')}`")
    lines.append("")

    # ── 3. 测试结果 ──
    lines.append("## 3. 测试结果")
    lines.append("")

    if is_support:
        _write_support_results(lines, result)
    else:
        _write_app_results(lines, result)

    # ── 4. 测试结论 ──
    lines.append("## 4. 测试结论")
    lines.append("")
    if "error" in result:
        lines.append(f"**评测失败**：{result['error']}")
    else:
        lines.append("评测正常完成，各项指标数据见上表。")
    lines.append("")

    # ── 5. 附件清单 ──
    lines.append("## 5. 附件清单")
    lines.append("")
    lines.append("| 文件 | 说明 |")
    lines.append("|------|------|")
    lines.append("| `test_plan.md` | 测试大纲 |")
    lines.append("| `test_report.md` | 本测试报告 |")
    lines.append("| `test_report.json` | 结构化测试结果 |")
    lines.append(f"| `{job_cfg.get('script', 'job_script')}` | 原始作业脚本 |")
    lines.append("")
    lines.append("---")
    lines.append("*本测试报告由 PerfBench 自动生成，符合《高性能应用评测指标体系与规范(十四五试行)V1.0》§3.2 要求。*")

    # 写入 Markdown
    os.makedirs(output_dir, exist_ok=True)
    md_path = os.path.join(output_dir, "test_report.md")
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    # 写入 JSON
    json_report = {
        "meta": {
            "generated_at": datetime.now().isoformat(),
            "tool": "PerfBench-BUAAHPC v1.0",
            "mode": mode_name,
        },
        "environment": {
            "hardware": hardware_name,
            "processor": processor,
            "accelerator": accel_type,
            "granularity": granularity,
            "repeat": repeat,
            "aggregation": aggregation,
        },
        "config": config,
        "results": result,
    }
    json_path = os.path.join(output_dir, "test_report.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(json_report, f, ensure_ascii=False, indent=2)

    return md_path, json_path


def _write_app_results(lines: list, result: dict):
    """写入应用软件评测结果表格。"""
    report = result.get("scalability_report", [])
    if not report:
        lines.append("*无可扩展性数据*")
        lines.append("")
        return

    lines.append("### 3.1 可扩展性结果")
    lines.append("")
    lines.append("| 核数 | 运行时间(s) | 加速比 | 并行效率(%) |")
    lines.append("|------|-------------|--------|-------------|")
    for entry in report:
        cores = entry.get("cores", "N/A")
        time_val = entry.get("time", "N/A")
        speedup = entry.get("speedup", 0)
        eff = entry.get("efficiency", 0)
        if isinstance(time_val, float):
            time_val = f"{time_val:.2f}"
        lines.append(f"| {cores} | {time_val} | {speedup:.2f} | {eff:.2f} |")
    lines.append("")

    # 精度结果（如有）
    accuracy = result.get("accuracy_report")
    if accuracy:
        lines.append("### 3.2 数值模拟精度")
        lines.append("")
        lines.append(f"- 相对误差：{accuracy.get('relative_error', 'N/A')}")
        lines.append(f"- RMSE：{accuracy.get('rmse', 'N/A')}")
        lines.append("")


def _write_support_results(lines: list, result: dict):
    """写入支撑软件评测结果表格。"""
    improvements = result.get("improvements", {})
    if not improvements:
        lines.append("*无性能提升数据*")
        lines.append("")
        return

    lines.append("### 3.1 性能提升结果")
    lines.append("")
    lines.append("| 指标类别 | 提升率(%) | 说明 |")
    lines.append("|----------|-----------|------|")
    _desc = {
        "exec_perf": "执行性能提升",
        "io": "I/O 性能提升",
        "compile": "编译优化提升",
        "mixed_precision": "混合精度提升",
        "autotune": "自动调优提升",
    }
    for metric, value in improvements.items():
        desc = _desc.get(metric, metric)
        if isinstance(value, dict):
            val_str = json.dumps(value, ensure_ascii=False)
        else:
            val_str = f"{value:.2f}" if isinstance(value, float) else str(value)
        lines.append(f"| {metric} | {val_str} | {desc} |")
    lines.append("")

    # before/after 详细数据
    before_data = result.get("before_results", {})
    after_data = result.get("after_results", {})
    if before_data or after_data:
        lines.append("### 3.2 前后对比详细数据")
        lines.append("")
        lines.append("| 阶段 | 规模 | 运行时间(s) |")
        lines.append("|------|------|-------------|")
        for label, data in [("before", before_data), ("after", after_data)]:
            sr = data.get("scalability_report", [])
            for entry in sr:
                cores = entry.get("cores", "N/A")
                t = entry.get("time", "N/A")
                if isinstance(t, float):
                    t = f"{t:.2f}"
                lines.append(f"| {label} | {cores} | {t} |")
        lines.append("")
