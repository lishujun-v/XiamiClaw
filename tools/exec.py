#!/usr/bin/env python3
"""
Exec Tool - 执行沙盒命令行

参数:
    command: 要执行的命令
    timeout: 超时时间(秒，默认 30)
    background: 是否在后台执行 (默认 False)
"""

import os
import sys
import subprocess
import shlex
from typing import Optional

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def execute(command: str, timeout: Optional[int] = None, background: bool = False) -> dict:
    """
    执行沙盒命令行

    Args:
        command: 要执行的命令
        timeout: 超时时间(秒，默认 30)
        background: 是否在后台执行 (默认 False)

    Returns:
        dict: 包含 success 和 content/error
    """
    if timeout is None:
        timeout = 30

    try:
        if background:
            # 后台执行
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            return {
                "success": True,
                "content": f"命令已在后台启动，PID: {process.pid}"
            }
        else:
            # 同步执行
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )

            # 组合 stdout 和 stderr
            output = result.stdout
            if result.stderr:
                if output:
                    output += "\n"
                output += result.stderr

            if result.returncode == 0:
                return {
                    "success": True,
                    "content": output if output else "命令执行成功 (无输出)"
                }
            else:
                return {
                    "success": False,
                    "error": f"命令执行失败 (退出码: {result.returncode})\n{output}",
                    "content": output,
                    "exit_code": result.returncode
                }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": f"命令执行超时 (超时时间: {timeout} 秒)"
        }
    except PermissionError:
        return {
            "success": False,
            "error": "权限不足，无法执行命令"
        }
    except FileNotFoundError as e:
        return {
            "success": False,
            "error": f"命令不存在: {str(e)}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"执行命令失败: {str(e)}"
        }


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="执行沙盒命令行")
    parser.add_argument("command", help="要执行的命令")
    parser.add_argument("--timeout", "-t", type=int, default=30,
                        help="超时时间(秒，默认 30)")
    parser.add_argument("--background", "-b", dest="background", action="store_true",
                        help="是否在后台执行")

    args = parser.parse_args()

    result = execute(args.command, args.timeout, args.background)

    if result["success"]:
        print(result["content"])
    else:
        print(f"错误: {result['error']}", file=sys.stderr)
        exit_code = result.get("exit_code", 1)
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
