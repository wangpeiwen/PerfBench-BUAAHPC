#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
单元测试：perfbench.utils.script_parser
测试脚本解析功能
"""
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from perfbench.utils.script_parser import parse_slurm_script


class TestParseSlurmScript:
    """测试 SLURM 脚本解析"""
    
    def test_parse_basic_script(self):
        """测试解析基础脚本"""
        script_content = """#!/bin/bash
#SBATCH --job-name=test_job
#SBATCH --nodes=4
#SBATCH --ntasks-per-node=2
#SBATCH --cpus-per-task=8
#SBATCH --time=01:00:00
#SBATCH --partition=cpu
#SBATCH --output=output.log
#SBATCH --error=error.log

srun -N 4 ./myapp
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.slurm', delete=False) as f:
            f.write(script_content)
            f.flush()
            
            try:
                info = parse_slurm_script(f.name)
                
                assert info["job_name"] == "test_job"
                assert info["nodes"] == 4
                assert info["tasks_per_node"] == 2
                assert info["cpus_per_task"] == 8
                assert info["time_limit"] == "01:00:00"
                assert info["partition"] == "cpu"
                assert info["output"] == "output.log"
                assert info["error"] == "error.log"
                assert len(info["commands"]) > 0
            finally:
                os.unlink(f.name)
    
    def test_parse_minimal_script(self):
        """测试解析最小脚本"""
        script_content = """#!/bin/bash

./myapp
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.slurm', delete=False) as f:
            f.write(script_content)
            f.flush()
            
            try:
                info = parse_slurm_script(f.name)
                
                # 检查默认值
                assert info["nodes"] == 1
                assert info["tasks_per_node"] == 1
                assert info["cpus_per_task"] == 1
                assert len(info["commands"]) > 0
            finally:
                os.unlink(f.name)
    
    def test_parse_multiple_commands(self):
        """测试解析多条命令"""
        script_content = """#!/bin/bash
#SBATCH --job-name=multi_cmd

echo "Starting job"
./compile.sh
./run.sh
echo "Job complete"
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.slurm', delete=False) as f:
            f.write(script_content)
            f.flush()
            
            try:
                info = parse_slurm_script(f.name)
                
                assert len(info["commands"]) == 4
                assert "Starting job" in info["commands"][0]
                assert "compile.sh" in info["commands"][1]
            finally:
                os.unlink(f.name)
    
    def test_parse_with_equals_sign(self):
        """测试解析使用等号的参数"""
        script_content = """#!/bin/bash
#SBATCH --job-name=test_job
#SBATCH --nodes=2
#SBATCH --time=02:30:00

echo "test"
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.slurm', delete=False) as f:
            f.write(script_content)
            f.flush()
            
            try:
                info = parse_slurm_script(f.name)
                
                assert info["job_name"] == "test_job"
                assert info["nodes"] == 2
                assert info["time_limit"] == "02:30:00"
            finally:
                os.unlink(f.name)
    
    def test_parse_with_space_separator(self):
        """测试解析使用空格分隔的参数"""
        script_content = """#!/bin/bash
#SBATCH --job-name test_job
#SBATCH --nodes 3
#SBATCH --cpus-per-task 4

echo "test"
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.slurm', delete=False) as f:
            f.write(script_content)
            f.flush()
            
            try:
                info = parse_slurm_script(f.name)
                
                assert info["job_name"] == "test_job"
                assert info["nodes"] == 3
                assert info["cpus_per_task"] == 4
            finally:
                os.unlink(f.name)
    
    def test_parse_nonexistent_file(self):
        """测试解析不存在的文件"""
        result = parse_slurm_script("/nonexistent/file.slurm")
        assert result is None
    
    def test_parse_complex_job_name(self):
        """测试解析复杂的job名称"""
        script_content = """#!/bin/bash
#SBATCH --job-name=my-job_v2.1

echo "test"
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.slurm', delete=False) as f:
            f.write(script_content)
            f.flush()
            
            try:
                info = parse_slurm_script(f.name)
                
                assert info["job_name"] == "my-job_v2.1"
            finally:
                os.unlink(f.name)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
