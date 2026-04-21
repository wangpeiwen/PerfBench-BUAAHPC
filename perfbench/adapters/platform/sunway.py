#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
申威（Sunway）平台适配器。

将原散落在 script_processor.py 和 monitoring.py 中的申威相关逻辑
收拢到此单一适配器，消除主流程中的 if is_sunway 分支。
"""

import os
import re
import subprocess
import time
from perfbench.adapters.platform.base import PlatformAdapter
from perfbench.utils.logger import get_logger
from perfbench.utils.monitoring import start_bjob_monitoring_on_login
from perfbench.utils.script_parser import parse_sunway_script

logger = get_logger()


class SunwayAdapter(PlatformAdapter):
    """
    申威平台适配器，封装 bsub / bjobs / cnload 等命令集合。

    注：申威平台当前不对提交脚本做改写，直接提交原始脚本。
    SLURM 解析器（parse_slurm_script）被复用做基础字段提取，
    因申威脚本格式与 SLURM 有相似结构，后续可按需替换为专用解析器。
    """

    # ------------------------------------------------------------------
    # 脚本解析
    # ------------------------------------------------------------------

    def parse_script(self, script_path: str) -> dict:
        """使用申威专用解析器，从 bsub 命令行提取参数。"""
        return parse_sunway_script(script_path)

    # ------------------------------------------------------------------
    # 脚本准备（提交前逻辑）
    # ------------------------------------------------------------------

    def prepare_script(self, script_path: str, script_info: dict,
                       interval: int, output_dir: str) -> str:
        """
        申威平台无脚本改写步骤，直接返回原始脚本路径。

        Args:
            script_path: 原始脚本路径（直接提交）
            script_info: 解析得到的脚本信息（本方法不使用）
            interval:    监控间隔（本方法不使用）
            output_dir:  输出目录（本方法不使用）

        Returns:
            str: 原始脚本路径，不做修改
        """
        logger.info(f"[Sunway] 申威平台不做脚本改写，直接提交原始脚本: {script_path}")
        return script_path

    # ------------------------------------------------------------------
    # 作业提交
    # ------------------------------------------------------------------

    def submit_job(self, script_path: str) -> str:
        """
        直接执行申威 wrapper 脚本（脚本内部调用 bsub），从 stdout 提取 JobID。

        申威脚本是 csh/bash wrapper，内部自行调用 bsub 并输出 JobID。
        典型输出包含 "Job <12345>" 格式。
        """
        try:
            script_dir = os.path.dirname(os.path.abspath(script_path))
            result = subprocess.run(
                [os.path.abspath(script_path)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                cwd=script_dir,
            )
            combined = result.stdout + result.stderr
            if result.returncode != 0:
                raise RuntimeError(f"申威脚本执行失败: {combined.strip()}")

            match = re.search(r'Job\s*<(\d+)>', combined)
            if not match:
                match = re.search(r'(\d+)', combined)
            if not match:
                raise RuntimeError(
                    f"无法从脚本输出中提取 JobID: {combined.strip()}"
                )
            jobid = match.group(1)
            logger.info(f"[Sunway] 申威作业已提交, JobID={jobid}")
            return jobid
        except FileNotFoundError:
            raise RuntimeError(f"脚本不存在或无执行权限: {script_path}")
        except PermissionError:
            raise RuntimeError(
                f"脚本无执行权限，请执行: chmod +x {script_path}"
            )

    # ------------------------------------------------------------------
    # 登录节点监控
    # ------------------------------------------------------------------

    def start_monitoring(self, jobid: str, interval: int, output_dir: str) -> int:
        """
        在登录节点后台启动 bjobs / cnload 周期采集脚本。

        Returns:
            int: 监控进程 PID
        """
        pid = start_bjob_monitoring_on_login(jobid, interval, output_dir)
        logger.info(f"[Sunway] 登录节点申威监控已启动 (pid={pid})")
        return pid

    # ------------------------------------------------------------------
    # 等待作业完成
    # ------------------------------------------------------------------

    def wait_for_job(self, jobid: str, poll_interval: int = 10) -> str:
        """
        轮询 bjobs 等待作业进入终态（DONE / EXIT / CANCELED / TERM）。

        Returns:
            str: 作业最终状态
        """
        logger.info(f"[Sunway] 等待申威作业 {jobid} 完成...")
        while True:
            try:
                result = subprocess.run(
                    ['bjobs', jobid],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                )
                lines = result.stdout.strip().splitlines()
                for line in lines:
                    parts = line.split()
                    if parts and parts[0] == jobid:
                        state = parts[1]
                        if state in ('DONE', 'EXIT', 'CANCELED', 'TERM'):
                            logger.info(f"[Sunway] 申威作业 {jobid} 已结束，状态: {state}")
                            return state
                        break
            except Exception as e:
                logger.warning(f"[Sunway] 查询申威作业状态时出错: {e}")
            time.sleep(poll_interval)

    # ------------------------------------------------------------------
    # 日志命令名
    # ------------------------------------------------------------------

    def get_log_cmd_name(self) -> str:
        """返回申威平台日志解析使用的命令名称。"""
        return "bjobs"
