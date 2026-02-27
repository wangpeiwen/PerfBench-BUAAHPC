#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
单元测试：perfbench.report.certificate_generator
测试证书生成功能，包括暗水印验证
"""
import os
import sys
import tempfile
import hashlib
import hmac

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    import pytest
except ImportError:
    pytest = None


class TestCertificateGenerator:
    """测试证书生成"""
    
    def test_generate_watermark_hash(self):
        """测试生成暗水印哈希"""
        from perfbench.report.certificate_generator import generate_watermark_hash
        
        # 测试基本功能
        watermark_data = {
            "timestamp": "2024-02-27T10:00:00Z",
            "platform": "HYGON",
            "version": "1.0.0"
        }
        
        secret_key = "perfbench_secret"
        watermark_hash = generate_watermark_hash(watermark_data, secret_key)
        
        assert isinstance(watermark_hash, str)
        assert len(watermark_hash) == 64  # SHA256 哈希的十六进制表示为64个字符
    
    def test_watermark_hash_consistency(self):
        """测试暗水印哈希的一致性"""
        from perfbench.report.certificate_generator import generate_watermark_hash
        
        watermark_data = {
            "timestamp": "2024-02-27T10:00:00Z",
            "platform": "HYGON"
        }
        
        secret_key = "test_secret"
        hash1 = generate_watermark_hash(watermark_data, secret_key)
        hash2 = generate_watermark_hash(watermark_data, secret_key)
        
        assert hash1 == hash2  # 相同输入应产生相同哈希
    
    def test_watermark_hash_different_inputs(self):
        """测试暗水印对不同输入的响应"""
        from perfbench.report.certificate_generator import generate_watermark_hash
        
        data1 = {"platform": "HYGON", "version": "1.0.0"}
        data2 = {"platform": "HYGON", "version": "1.0.1"}
        secret_key = "test_secret"
        
        hash1 = generate_watermark_hash(data1, secret_key)
        hash2 = generate_watermark_hash(data2, secret_key)
        
        assert hash1 != hash2  # 不同输入应产生不同哈希
    
    def test_verify_watermark(self):
        """测试验证暗水印"""
        from perfbench.report.certificate_generator import (
            generate_watermark_hash, 
            verify_watermark
        )
        
        watermark_data = {
            "timestamp": "2024-02-27T10:00:00Z",
            "platform": "HYGON"
        }
        secret_key = "test_secret"
        
        # 生成水印
        watermark_hash = generate_watermark_hash(watermark_data, secret_key)
        
        # 验证水印
        is_valid = verify_watermark(watermark_data, watermark_hash, secret_key)
        assert is_valid is True
    
    def test_verify_watermark_invalid(self):
        """测试验证无效水印"""
        from perfbench.report.certificate_generator import verify_watermark
        
        watermark_data = {
            "timestamp": "2024-02-27T10:00:00Z",
            "platform": "HYGON"
        }
        secret_key = "test_secret"
        invalid_hash = "0" * 64  # 假的哈希
        
        # 验证应该失败
        is_valid = verify_watermark(watermark_data, invalid_hash, secret_key)
        assert is_valid is False
    
    def test_embed_watermark_in_text(self):
        """测试在文本中嵌入暗水印"""
        from perfbench.report.certificate_generator import embed_text_watermark
        
        original_text = "This is a test document"
        watermark = "abc123"
        
        watermarked_text = embed_text_watermark(original_text, watermark)
        
        assert len(watermarked_text) > len(original_text)  # 水印应该增加文本长度
        assert original_text in watermarked_text  # 原始文本应该被保留
    
    def test_extract_watermark_from_text(self):
        """测试从文本中提取暗水印"""
        from perfbench.report.certificate_generator import (
            embed_text_watermark, 
            extract_text_watermark
        )
        
        original_text = "Document content"
        watermark = "xyz789"
        
        watermarked_text = embed_text_watermark(original_text, watermark)
        extracted_watermark = extract_text_watermark(watermarked_text)
        
        assert extracted_watermark == watermark
    
    def test_report_info_structure(self):
        """测试报告信息结构"""
        report_info = {
            "platform": "HYGON",
            "node_num": "100",
            "app_name": "LAMMPS",
            "core_num": "102400",
            "eff": "18.30%(10 Nodes)",
            "time": "2025-02-27",
        }
        
        # 验证必须字段
        required_fields = ["platform", "node_num", "app_name", "core_num", "eff", "time"]
        for field in required_fields:
            assert field in report_info
            assert report_info[field] is not None


class TestWatermarkIntegration:
    """测试水印集成"""
    
    def test_full_watermark_workflow(self):
        """测试完整的水印工作流程"""
        from perfbench.report.certificate_generator import (
            generate_watermark_hash,
            verify_watermark,
            embed_text_watermark,
            extract_text_watermark
        )
        
        # 1. 创建水印数据
        watermark_data = {
            "platform": "HYGON",
            "timestamp": "2024-02-27T10:00:00Z",
            "node_num": "100"
        }
        secret_key = "perfbench_cert_secret"
        
        # 2. 生成水印哈希
        watermark_hash = generate_watermark_hash(watermark_data, secret_key)
        
        # 3. 验证生成的水印
        assert verify_watermark(watermark_data, watermark_hash, secret_key)
        
        # 4. 在文档中嵌入水印
        document_text = f"Performance Report\nPlatform: {watermark_data['platform']}"
        watermarked_doc = embed_text_watermark(document_text, watermark_hash)
        
        # 5. 从文档中提取水印
        extracted_hash = extract_text_watermark(watermarked_doc)
        
        # 6. 验证提取的水印
        assert verify_watermark(watermark_data, extracted_hash, secret_key)


if __name__ == '__main__':
    if pytest:
        pytest.main([__file__, '-v'])
    else:
        print("pytest not installed, skipping tests")
