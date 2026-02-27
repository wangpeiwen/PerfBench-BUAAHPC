#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
证书验证工具：用于验证生成的证书海报的真伪
"""
import os
import json
import sys
import hashlib
import hmac

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from perfbench.report.certificate_generator import (
    verify_watermark,
    WATERMARK_SECRET_KEY
)


def verify_certificate(watermark_file):
    """
    验证证书的水印信息
    
    Args:
        watermark_file (str): 水印信息文件路径
    
    Returns:
        bool: 证书是否有效
    """
    try:
        if not os.path.exists(watermark_file):
            print(f"错误：水印文件不存在: {watermark_file}")
            return False
        
        # 读取水印信息
        with open(watermark_file, 'r', encoding='utf-8') as f:
            watermark_info = json.load(f)
        
        # 提取验证所需的信息
        stored_hash = watermark_info.get("watermark_hash")
        watermark_data = watermark_info.get("watermark_data")
        verification_code = watermark_info.get("verification_code")
        
        if not all([stored_hash, watermark_data, verification_code]):
            print("错误：水印文件格式不完整")
            return False
        
        # 验证水印
        is_valid = verify_watermark(watermark_data, stored_hash)
        
        if is_valid:
            print("✓ 证书验证成功！")
            print(f"  平台: {watermark_data.get('platform')}")
            print(f"  节点数: {watermark_data.get('node_num')}")
            print(f"  应用: {watermark_data.get('app_name')}")
            print(f"  验证码: {verification_code}")
            print(f"  生成时间: {watermark_info.get('generated_time')}")
            return True
        else:
            print("✗ 证书验证失败！水印哈希不匹配，证书可能被篡改")
            return False
    
    except json.JSONDecodeError:
        print("错误：水印文件格式错误（无效的JSON）")
        return False
    except Exception as e:
        print(f"验证过程出错: {str(e)}")
        return False


def list_certificates(output_dir):
    """
    列出输出目录中所有的证书及其水印信息
    
    Args:
        output_dir (str): 输出目录路径
    """
    if not os.path.exists(output_dir):
        print(f"目录不存在: {output_dir}")
        return
    
    watermark_files = []
    for file in os.listdir(output_dir):
        if file.endswith("_watermark.json"):
            watermark_files.append(os.path.join(output_dir, file))
    
    if not watermark_files:
        print(f"在 {output_dir} 中未找到任何证书水印文件")
        return
    
    print(f"找到 {len(watermark_files)} 个证书：\n")
    for watermark_file in watermark_files:
        try:
            with open(watermark_file, 'r', encoding='utf-8') as f:
                info = json.load(f)
            
            data = info.get("watermark_data", {})
            print(f"• {info.get('pdf_file', 'unknown')}")
            print(f"  平台: {data.get('platform')}")
            print(f"  验证码: {info.get('verification_code')}")
            print()
        except Exception as e:
            print(f"  读取失败: {str(e)}\n")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法:")
        print("  验证单个证书: python verify_certificate.py <watermark_file>")
        print("  列出目录中的证书: python verify_certificate.py --list <output_dir>")
        sys.exit(1)
    
    if sys.argv[1] == '--list':
        if len(sys.argv) < 3:
            print("错误: 请指定输出目录")
            sys.exit(1)
        list_certificates(sys.argv[2])
    else:
        is_valid = verify_certificate(sys.argv[1])
        sys.exit(0 if is_valid else 1)
