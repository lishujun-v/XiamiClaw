#!/usr/bin/env python3
"""
Write Tool - 创建或覆盖文件

参数:
    file_path: 文件路径
    content: 文件内容
"""

import os
import sys
from typing import Optional

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def execute(file_path: str, content: str) -> dict:
    """
    创建或覆盖文件

    Args:
        file_path: 文件路径
        content: 文件内容

    Returns:
        dict: 包含 success 和 content/error
    """
    try:
        # 确保父目录存在
        parent_dir = os.path.dirname(file_path)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)

        # 写入文件
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

        return {
            "success": True,
            "content": f"已写入 {len(content)} 字符到 {file_path}"
        }

    except PermissionError:
        return {
            "success": False,
            "error": f"权限不足，无法写入文件: {file_path}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"写入文件失败: {str(e)}"
        }


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="创建或覆盖文件")
    parser.add_argument("file_path", help="文件路径")
    parser.add_argument("content", nargs="?", default="", help="文件内容 (支持从stdin读取)")

    args = parser.parse_args()

    # 如果没有提供内容，尝试从 stdin 读取
    content = args.content
    if not content:
        content = sys.stdin.read()

    result = execute(args.file_path, content)

    if result["success"]:
        print(result["content"])
    else:
        print(f"错误: {result['error']}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
