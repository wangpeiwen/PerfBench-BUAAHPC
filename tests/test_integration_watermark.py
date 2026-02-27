#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
集成测试：验证完整的证书生成和水印验证工作流
"""
import os
import sys
import json
import tempfile
import shutil

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from perfbench.report.certificate_generator import (
    generate_watermark_hash,
    verify_watermark,
    embed_text_watermark,
    extract_text_watermark
)
from perfbench.report.verify_certificate import verify_certificate


def test_complete_watermark_workflow():
    """测试完整的水印工作流程"""
    print("=" * 60)
    print("开始集成测试：完整的水印验证工作流")
    print("=" * 60)
    
    # 1. 创建临时目录
    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"\n[1] 创建临时目录: {tmpdir}")
        
        # 2. 模拟报告信息
        report_info = {
            "platform": "HYGON",
            "node_num": "100",
            "app_name": "LAMMPS",
            "core_num": "102400",
            "eff": "18.30%(10 Nodes)",
            "time": "2025-02-27 10:00:00"
        }
        print(f"\n[2] 报告信息:")
        for key, value in report_info.items():
            print(f"    {key}: {value}")
        
        # 3. 生成水印数据
        watermark_data = {
            "platform": report_info["platform"],
            "node_num": report_info["node_num"],
            "app_name": report_info["app_name"],
            "timestamp": "2025-02-27T10:00:00Z",
            "version": "1.0.0"
        }
        print(f"\n[3] 生成水印数据")
        
        # 4. 生成水印哈希
        watermark_hash = generate_watermark_hash(watermark_data)
        verification_code = watermark_hash[:16].upper()
        print(f"\n[4] 生成水印:")
        print(f"    哈希值: {watermark_hash}")
        print(f"    验证码: {verification_code}")
        
        # 5. 验证水印
        is_valid = verify_watermark(watermark_data, watermark_hash)
        print(f"\n[5] 验证生成的水印: {'✓ 成功' if is_valid else '✗ 失败'}")
        assert is_valid, "水印验证失败"
        
        # 6. 创建水印文件
        watermark_file = os.path.join(tmpdir, "certificate_watermark.json")
        watermark_info = {
            "watermark_hash": watermark_hash,
            "verification_code": verification_code,
            "watermark_data": watermark_data,
            "generated_time": "2025-02-27T10:00:00Z",
            "pdf_file": "certificate_final.pdf"
        }
        
        with open(watermark_file, 'w', encoding='utf-8') as f:
            json.dump(watermark_info, f, indent=2, ensure_ascii=False)
        print(f"\n[6] 创建水印文件: {watermark_file}")
        
        # 7. 测试文本水印嵌入和提取
        document_text = f"Performance Report\nPlatform: {report_info['platform']}"
        watermarked_doc = embed_text_watermark(document_text, watermark_hash)
        extracted_hash = extract_text_watermark(watermarked_doc)
        
        print(f"\n[7] 文本水印嵌入和提取:")
        print(f"    原始文本长度: {len(document_text)}")
        print(f"    水印后文本长度: {len(watermarked_doc)}")
        print(f"    提取的水印是否相同: {extracted_hash == watermark_hash}")
        assert extracted_hash == watermark_hash, "文本水印提取失败"
        
        # 8. 验证水印文件
        print(f"\n[8] 验证水印文件...")
        # 由于 verify_certificate 打印到控制台，我们需要模拟其行为
        with open(watermark_file, 'r', encoding='utf-8') as f:
            stored_info = json.load(f)
        
        stored_hash = stored_info.get("watermark_hash")
        stored_data = stored_info.get("watermark_data")
        
        is_file_valid = verify_watermark(stored_data, stored_hash)
        print(f"    水印文件验证: {'✓ 成功' if is_file_valid else '✗ 失败'}")
        assert is_file_valid, "水印文件验证失败"
        
        # 9. 测试被篡改的水印
        print(f"\n[9] 测试被篡改的水印...")
        tampered_hash = watermark_hash[:-1] + ('0' if watermark_hash[-1] != '0' else '1')
        is_tampered_valid = verify_watermark(watermark_data, tampered_hash)
        print(f"    被篡改水印应该验证失败: {'✓ 正确' if not is_tampered_valid else '✗ 错误'}")
        assert not is_tampered_valid, "篡改检测失败"
        
        # 10. 测试被篡改的数据
        print(f"\n[10] 测试数据完整性...")
        tampered_data = watermark_data.copy()
        tampered_data["node_num"] = "200"  # 修改数据
        
        is_data_tampered = verify_watermark(tampered_data, watermark_hash)
        print(f"    修改后的数据应该验证失败: {'✓ 正确' if not is_data_tampered else '✗ 错误'}")
        assert not is_data_tampered, "数据篡改检测失败"
    
    print("\n" + "=" * 60)
    print("✓ 所有集成测试通过！")
    print("=" * 60)


def test_watermark_hash_stability():
    """测试水印哈希的稳定性"""
    print("\n测试水印哈希的稳定性...")
    
    data = {
        "platform": "HYGON",
        "node_num": "100",
        "timestamp": "2025-02-27T10:00:00Z"
    }
    
    # 生成多个哈希，应该都相同
    hashes = [generate_watermark_hash(data) for _ in range(5)]
    
    assert len(set(hashes)) == 1, "相同数据应该生成相同哈希"
    print(f"  ✓ 5次哈希生成结果一致")
    
    # 改变数据顺序，哈希应该仍然相同（JSON 顺序无关）
    data2 = {
        "timestamp": "2025-02-27T10:00:00Z",
        "platform": "HYGON",
        "node_num": "100"
    }
    
    hash1 = generate_watermark_hash(data)
    hash2 = generate_watermark_hash(data2)
    
    assert hash1 == hash2, "字段顺序不应该影响哈希结果"
    print(f"  ✓ 字段顺序不影响哈希结果")


def test_verification_code_generation():
    """测试验证码生成"""
    print("\n测试验证码生成...")
    
    data1 = {
        "platform": "HYGON",
        "node_num": "100"
    }
    
    data2 = {
        "platform": "HYGON",
        "node_num": "200"  # 不同节点数
    }
    
    hash1 = generate_watermark_hash(data1)
    hash2 = generate_watermark_hash(data2)
    
    code1 = hash1[:16].upper()
    code2 = hash2[:16].upper()
    
    assert code1 != code2, "不同数据应该生成不同验证码"
    assert len(code1) == 16, "验证码应该是16个字符"
    assert code1.isalnum(), "验证码应该是十六进制数字"
    
    print(f"  ✓ 验证码生成正确: {code1}")


if __name__ == '__main__':
    try:
        test_complete_watermark_workflow()
        test_watermark_hash_stability()
        test_verification_code_generation()
        print("\n✓ 所有集成测试执行成功！")
        sys.exit(0)
    except AssertionError as e:
        print(f"\n✗ 测试失败: {str(e)}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ 测试异常: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
