#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Orchestrator 包初始化。

提供测试配置加载（YAML 格式）和编排引擎入口。
"""

from perfbench.orchestrator.config_loader import load_test_config

__all__ = ["load_test_config"]
