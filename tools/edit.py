#!/usr/bin/env python3
"""
Edit Tool - 精确编辑文件

参数:
    file_path: 文件路径
    old_string: 要替换的原始字符串
    new_string: 替换后的新字符串
    replace_all: 是否替换所有匹配项 (默认 False)
"""

import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def execute(file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> dict:
    """
    精确编辑文件

    Args:
        file_path: 文件路径
        old_string: 要替换的原始字符串
        new_string: 替换后的新字符串
        replace_all: 是否替换所有匹配项 (默认 False)

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

        # 读取文件内容
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 检查 old_string 是否存在
        if old_string not in content:
            return {
                "success": False,
                "error": "文件中未找到要替换的字符串"
            }

        # 执行替换
        if replace_all:
            new_content = content.replace(old_string, new_string)
            count = content.count(old_string)
        else:
            new_content = content.replace(old_string, new_string, 1)
            count = 1

        # 写回文件
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)

        return {
            "success": True,
            "content": f"已替换 {count} 处，文件已更新: {file_path}"
        }

    except PermissionError:
        return {
            "success": False,
            "error": f"权限不足，无法编辑文件: {file_path}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"编辑文件失败: {str(e)}"
        }


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="精确编辑文件")
    parser.add_argument("file_path", help="文件路径")
    parser.add_argument("old_string", help="要替换的原始字符串")
    parser.add_argument("new_string", help="替换后的新字符串")
    parser.add_argument("--all", "-a", dest="replace_all", action="store_true",
                        help="替换所有匹配项 (默认只替换第一个)")

    args = parser.parse_args()

    result = execute(args.file_path, args.old_string, args.new_string, args.replace_all)

    if result["success"]:
        print(result["content"])
    else:
        print(f"错误: {result['error']}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
