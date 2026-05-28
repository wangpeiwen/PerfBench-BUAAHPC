#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多规模自动提交编排引擎。

职责：
    1. 读取测试配置中的规模列表
    2. 对每个规模生成脚本副本（替换节点数/数据集占位符）
    3. 调用 PlatformAdapter 提交、监控、等待
    4. 收集各规模运行时间
    5. 调用 scalability 模块计算并行效率
    6. 支持重复测试 + 结果聚合

不直接执行调度命令，所有平台交互通过 PlatformAdapter 抽象层完成。
"""

import os
import re
import shutil
import statistics
import time
from typing import List, Optional

from perfbench.utils.logger import get_logger
from perfbench.analysis.metrics import calculate_parallelism
from perfbench.analysis.scalability import multi_scale_report

logger = get_logger()


class MultiScaleOrchestrator:
    """多规模测试编排器。"""

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

        # 解析配置
        self.global_cfg = config.get("global", {})
        self.scaling_cfg = config.get("scaling", {})
        self.job_cfg = config.get("job", {})

        self.granularity = self.global_cfg.get("granularity", "board")
        self.repeat = max(1, self.global_cfg.get("repeat", 1))
        self.aggregation = self.global_cfg.get("aggregation", "mean")

        self.mode = self.scaling_cfg.get("mode", "strong")
        self.scales = self.scaling_cfg.get("scales", [1])
        self.datasets = self.scaling_cfg.get("datasets", [])
        self.compute_ratios = self.scaling_cfg.get("compute_ratios", [])

        self.script_path = self.job_cfg.get("script", "")
        self.node_placeholder = self.job_cfg.get("node_placeholder", "__NODES__")
        self.dataset_placeholder = self.job_cfg.get("dataset_placeholder", "__DATASET__")

    def run(self) -> dict:
        """
        执行多规模测试。

        Returns:
            dict: {
                "mode": str,
                "granularity": str,
                "scales": list,
                "results": list of per-scale results,
                "scalability_report": list from multi_scale_report(),
                "aggregated_times": list of aggregated times per scale,
            }
        """
        logger.info(f"开始多规模测试: mode={self.mode}, scales={self.scales}, "
                    f"repeat={self.repeat}, granularity={self.granularity}")

        all_scale_results = []

        for i, scale in enumerate(self.scales):
            scale_dir = os.path.join(self.output_dir, f"scale_{scale}")
            os.makedirs(scale_dir, exist_ok=True)

            # 生成该规模的脚本
            script_content = self._read_script()
            if script_content is None:
                logger.error(f"无法读取脚本: {self.script_path}")
                return {"error": "script_read_failed"}

            script_content = self._substitute_placeholders(
                script_content, scale, i)

            modified_script_path = os.path.join(scale_dir, "job_script.sh")
            with open(modified_script_path, "w", encoding="utf-8") as f:
                f.write(script_content)

            # 重复测试
            run_times = []
            for r in range(self.repeat):
                run_dir = os.path.join(scale_dir, f"run_{r+1}") if self.repeat > 1 else scale_dir
                if self.repeat > 1:
                    os.makedirs(run_dir, exist_ok=True)
                    run_script = os.path.join(run_dir, "job_script.sh")
                    shutil.copy2(modified_script_path, run_script)
                else:
                    run_script = modified_script_path

                elapsed = self._submit_and_wait(run_script, run_dir)
                if elapsed is not None:
                    run_times.append(elapsed)
                    logger.info(f"  scale={scale}, run={r+1}/{self.repeat}, "
                                f"elapsed={elapsed:.2f}s")
                else:
                    logger.warning(f"  scale={scale}, run={r+1} 失败")

            # 聚合
            agg_time = self._aggregate(run_times) if run_times else None

            all_scale_results.append({
                "scale": scale,
                "run_times": run_times,
                "aggregated_time": agg_time,
            })

        # 计算可扩展性指标
        aggregated_times = [r["aggregated_time"] for r in all_scale_results]
        cores_list = self._compute_cores_list()

        scalability_report = []
        if all(t is not None for t in aggregated_times) and len(aggregated_times) >= 2:
            F_s_list = self.compute_ratios if self.mode == "weak" else None
            scalability_report = multi_scale_report(
                aggregated_times, cores_list, mode=self.mode, F_s_list=F_s_list)

        result = {
            "mode": self.mode,
            "granularity": self.granularity,
            "scales": self.scales,
            "results": all_scale_results,
            "scalability_report": scalability_report,
            "aggregated_times": aggregated_times,
            "cores_list": cores_list,
        }

        logger.info(f"多规模测试完成: {len(self.scales)} 个规模")
        return result

    def _read_script(self) -> Optional[str]:
        """读取原始作业脚本内容。"""
        try:
            with open(self.script_path, "r", encoding="utf-8") as f:
                return f.read()
        except (FileNotFoundError, IOError):
            return None

    def _substitute_placeholders(self, content: str, scale: int,
                                 scale_index: int) -> str:
        """替换脚本中的占位符。"""
        content = content.replace(self.node_placeholder, str(scale))

        if self.mode == "weak" and self.datasets:
            if scale_index < len(self.datasets):
                content = content.replace(
                    self.dataset_placeholder, self.datasets[scale_index])

        return content

    def _submit_and_wait(self, script_path: str, work_dir: str) -> Optional[float]:
        """
        提交作业并等待完成，返回运行时间（秒）。

        通过 PlatformAdapter 的标准接口完成。
        """
        try:
            # prepare_script: 注入监控代码
            prepared_path = self.adapter.prepare_script(script_path, work_dir)

            # submit_job: 提交
            job_id = self.adapter.submit_job(prepared_path, work_dir)
            if not job_id:
                return None

            # start_monitoring: 启动监控（如有）
            self.adapter.start_monitoring(job_id, work_dir)

            # wait_for_job: 等待完成，返回运行时间
            elapsed = self.adapter.wait_for_job(job_id, work_dir)
            return elapsed

        except Exception as e:
            logger.error(f"作业执行失败: {e}")
            return None

    def _aggregate(self, times: List[float]) -> float:
        """根据配置的聚合方式计算结果。"""
        if not times:
            return 0.0
        if self.aggregation == "median":
            return statistics.median(times)
        elif self.aggregation == "min":
            return min(times)
        else:  # mean
            return statistics.mean(times)

    def _compute_cores_list(self) -> List[int]:
        """计算各规模对应的并行单元数。"""
        # 从 hardware_config 获取硬件名
        hardware_name = self.config.get("hardware_name", "")
        cores = []
        for scale in self.scales:
            info = calculate_parallelism(hardware_name, scale, self.granularity)
            if info:
                cores.append(info["core_num"])
            else:
                cores.append(scale)  # fallback: 直接用节点数
        return cores
