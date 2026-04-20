#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
前后对比编排引擎（支撑软件评测）。

职责：
    1. 分别对 before_script 和 after_script 执行多规模测试
    2. 对比两组结果，计算性能提升率
    3. 支持多种提升指标类型（exec_perf, io, compile, mixed_precision, autotune）

核心思路：支撑软件评测 = 应用评测 × 2（before/after）+ 增益计算
"""

import os
from typing import List, Optional

from perfbench.utils.logger import get_logger
from perfbench.orchestrator.multi_scale import MultiScaleOrchestrator
from perfbench.analysis.improvement import (
    execution_improvement,
    io_improvement,
    compile_optimization_improvement,
    mixed_precision_improvement,
    autotune_avg_improvement,
)

logger = get_logger()


class BeforeAfterOrchestrator:
    """支撑软件前后对比编排器。"""

    def __init__(self, config: dict, platform_adapter, output_dir: str):
        """
        Args:
            config:           load_test_config() 返回的完整配置字典
            platform_adapter: PlatformAdapter 实例
            output_dir:       输出根目录
        """
        self.config = config
        self.adapter = platform_adapter
        self.output_dir = output_dir

        self.support_cfg = config.get("support", {})
        self.metric_types = self.support_cfg.get("metric_types", ["exec_perf"])

    def run(self) -> dict:
        """
        执行支撑软件前后对比测试。

        Returns:
            dict: {
                "before_results": multi_scale result,
                "after_results": multi_scale result,
                "improvements": dict of metric_type -> improvement values,
            }
        """
        logger.info("开始支撑软件前后对比测试")

        # Phase A: Baseline（无支撑软件）
        before_dir = os.path.join(self.output_dir, "before")
        os.makedirs(before_dir, exist_ok=True)

        before_config = self._make_sub_config(
            self.support_cfg.get("before_script", ""))
        before_orch = MultiScaleOrchestrator(
            before_config, self.adapter, before_dir)
        before_results = before_orch.run()

        # Phase B: With Support Software
        after_dir = os.path.join(self.output_dir, "after")
        os.makedirs(after_dir, exist_ok=True)

        after_config = self._make_sub_config(
            self.support_cfg.get("after_script", ""))
        after_orch = MultiScaleOrchestrator(
            after_config, self.adapter, after_dir)
        after_results = after_orch.run()

        # Phase C: 增益计算
        improvements = self._compute_improvements(
            before_results, after_results)

        result = {
            "before_results": before_results,
            "after_results": after_results,
            "improvements": improvements,
        }

        logger.info("支撑软件前后对比测试完成")
        return result

    def _make_sub_config(self, script_path: str) -> dict:
        """基于主配置生成子编排配置，替换脚本路径。"""
        import copy
        sub = copy.deepcopy(self.config)
        sub.setdefault("job", {})["script"] = script_path
        return sub

    def _compute_improvements(self, before: dict, after: dict) -> dict:
        """根据 metric_types 计算各项提升率。"""
        improvements = {}

        before_times = before.get("aggregated_times", [])
        after_times = after.get("aggregated_times", [])

        for metric_type in self.metric_types:
            if metric_type == "exec_perf":
                improvements["exec_perf"] = self._pairwise_improvement(
                    before_times, after_times, execution_improvement)

            elif metric_type == "io":
                improvements["io"] = self._pairwise_improvement(
                    before_times, after_times, io_improvement)

            elif metric_type == "compile":
                # 编译优化用性能指标（越大越好），这里用 1/time 作为性能
                before_perf = [1.0/t if t and t > 0 else 0 for t in before_times]
                after_perf = [1.0/t if t and t > 0 else 0 for t in after_times]
                improvements["compile"] = self._pairwise_improvement(
                    before_perf, after_perf, compile_optimization_improvement)

            elif metric_type == "mixed_precision":
                improvements["mixed_precision"] = self._pairwise_improvement(
                    before_times, after_times, mixed_precision_improvement)

            elif metric_type == "autotune":
                apps = self.support_cfg.get("autotune_apps", [])
                if apps:
                    # autotune 需要多组应用的 before/after
                    improvements["autotune"] = self._autotune_result(apps)
                else:
                    improvements["autotune"] = self._pairwise_improvement(
                        before_times, after_times, execution_improvement)

        return improvements

    def _pairwise_improvement(self, before_vals: list, after_vals: list,
                              func) -> list:
        """对每个规模计算提升率。"""
        results = []
        for i in range(min(len(before_vals), len(after_vals))):
            b, a = before_vals[i], after_vals[i]
            if b is not None and a is not None:
                rate = func(b, a)
                results.append({"scale_index": i, "rate": rate})
            else:
                results.append({"scale_index": i, "rate": None})
        return results

    def _autotune_result(self, apps: list) -> Optional[dict]:
        """
        自动调优效果：多组应用的平均提升率。
        apps 格式: [{"before": path, "after": path}, ...]

        注意：autotune 模式需要独立提交每组应用，当前为占位实现，
        完整实现需要在 Phase 2 后续迭代中补充。
        """
        logger.warning("autotune 多应用模式为占位实现，需后续补充")
        return {"avg_rate": None, "per_app_rates": [], "note": "placeholder"}
