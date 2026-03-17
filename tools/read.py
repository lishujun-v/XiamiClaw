#!/usr/bin/env python3
"""
Read Tool - 读取文件内容

参数:
    file_path: 文件路径
    limit: 限制读取的行数 (可选)
    offset: 从第几行开始读取 (可选)
"""

import os
import sys
from typing import Optional

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def execute(file_path: str, limit: Optional[int] = None, offset: Optional[int] = None) -> dict:
    """
    读取文件内容

    Args:
        file_path: 文件路径
        limit: 限制读取的行数 (可选)
        offset: 从第几行开始读取 (可选，默认从第1行开始)

    Returns:
        dict: 包含 success 和 content/error
    """
    try:
        # 检查文件是否存在
        if not os.path.exists(file_path):
            return {
                "success": False,
                "error": f"文件不存在: {file_path}"
            }

        # 检查是否为文件
        if not os.path.isfile(file_path):
            return {
                "success": False,
                "error": f"路径不是文件: {file_path}"
            }

        # 读取文件内容
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # 处理 offset
        if offset is not None:
            if offset < 1:
                offset = 1
            lines = lines[offset - 1:]  # offset 是 1-based

        # 处理 limit
        if limit is not None:
            if limit > 0:
                lines = lines[:limit]

        content = ''.join(lines)

        return {
            "success": True,
            "content": content
        }

    except PermissionError:
        return {
            "success": False,
            "error": f"权限不足，无法读取文件: {file_path}"
        }
    except UnicodeDecodeError:
        # 尝试用其他编码读取
        try:
            with open(file_path, 'r', encoding='latin-1') as f:
                content = f.read()
            return {
                "success": True,
                "content": content
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"文件编码错误: {str(e)}"
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"读取文件失败: {str(e)}"
        }


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="读取文件内容")
    parser.add_argument("file_path", help="文件路径")
    parser.add_argument("--limit", type=int, help="限制读取的行数")
    parser.add_argument("--offset", type=int, help="从第几行开始读取")

    args = parser.parse_args()

    result = execute(args.file_path, args.limit, args.offset)

    if result["success"]:
        print(result["content"])
    else:
        print(f"错误: {result['error']}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
