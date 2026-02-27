#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
单元测试：perfbench.utils.result_handler
测试并行度计算和配置读取功能
"""
import os
import sys
import tempfile
import pytest
import yaml

# 确保可以导入 perfbench 模块
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from perfbench.utils.result_handler import calculate_parallelism, get_platform_config


class TestCalculateParallelism:
    """测试 calculate_parallelism 函数"""
    
    def test_sw26010(self):
        """测试 SW26010 平台"""
        result = calculate_parallelism("SW26010", 10)
        assert result["core_num"] == 2600
        assert "260" in result["method"]
    
    def test_sw39000(self):
        """测试 SW39000 平台"""
        result = calculate_parallelism("SW39000", 5)
        assert result["core_num"] == 1950
        assert "390" in result["method"]
    
    def test_feitian_64(self):
        """测试飞腾-64平台"""
        result = calculate_parallelism("飞腾-64", 8)
        assert result["core_num"] == 512
        assert "64" in result["method"]
    
    def test_matrix2000(self):
        """测试 Matrix2000 平台"""
        result = calculate_parallelism("Matrix2000", 4)
        assert result["core_num"] == 1024
        assert "256" in result["method"]
    
    def test_matrix3000(self):
        """测试 Matrix3000 平台"""
        result = calculate_parallelism("Matrix3000", 2)
        assert result["core_num"] == 3296
        assert "1648" in result["method"]
    
    def test_dcu_z100(self):
        """测试 DCU Z100 平台"""
        result = calculate_parallelism("DCU Z100", 6)
        assert result["core_num"] == 6 * 288  # 256 + 32
        assert "DCU" in result["method"]
    
    def test_dcu_z100l(self):
        """测试 DCU Z100L 平台"""
        result = calculate_parallelism("DCU Z100L", 3)
        assert result["core_num"] == 3 * 288  # 256 + 32
    
    def test_bw1000_80cu(self):
        """测试 BW1000(80CU) 平台"""
        result = calculate_parallelism("BW1000(80CU)", 5)
        assert result["core_num"] == 5 * 352  # 320 + 32
    
    def test_bw1000_88cu(self):
        """测试 BW1000(88CU) 平台"""
        result = calculate_parallelism("BW1000(88CU)", 4)
        assert result["core_num"] == 4 * 384  # 352 + 32
    
    def test_tesla_p100(self):
        """测试 Tesla P100 平台"""
        result = calculate_parallelism("Tesla P100", 10)
        assert result["core_num"] == 1120
        assert "112" in result["method"]
    
    def test_tesla_v100(self):
        """测试 Tesla V100 平台"""
        result = calculate_parallelism("Tesla V100", 8)
        assert result["core_num"] == 1280
        assert "160" in result["method"]
    
    def test_tesla_as100(self):
        """测试 Tesla As100 平台"""
        result = calculate_parallelism("Tesla As100", 6)
        assert result["core_num"] == 1296
        assert "216" in result["method"]
    
    def test_unsupported_platform(self):
        """测试不支持的平台"""
        result = calculate_parallelism("UnknownPlatform", 5)
        assert result is None
    
    def test_single_node(self):
        """测试单节点"""
        result = calculate_parallelism("SW26010", 1)
        assert result["core_num"] == 260
    
    def test_large_node_count(self):
        """测试大节点数"""
        result = calculate_parallelism("Matrix2000", 1000)
        assert result["core_num"] == 256000


class TestGetPlatformConfig:
    """测试 get_platform_config 函数"""
    
    def test_config_file_exists(self):
        """测试配置文件是否存在"""
        config = get_platform_config()
        assert config is not None
    
    def test_config_structure(self):
        """测试配置结构"""
        config = get_platform_config()
        assert "platform_name" in config
        assert "compared_cores" in config
        assert "compared_run_time" in config
    
    def test_config_values_types(self):
        """测试配置值的类型"""
        config = get_platform_config()
        assert isinstance(config["platform_name"], str)
        assert isinstance(config["compared_cores"], (int, float))
        assert isinstance(config["compared_run_time"], (int, float))
    
    def test_config_non_empty(self):
        """测试配置值不为空"""
        config = get_platform_config()
        assert config["platform_name"]
        assert config["compared_cores"] > 0
        assert config["compared_run_time"] > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
