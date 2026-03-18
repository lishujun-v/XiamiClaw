#!/usr/bin/env python3
"""
ClawHub Tool - 与 ClawHub 公开技能注册表交互

功能：
- 搜索公开的 skills
- 安装 skills 到本地
- 发布自己的 skills
- 更新已安装的 skills

前提：
- 需要先安装 clawhub: npm i -g clawhub
- 或者使用 bun/pnpm: pnpm add -g clawhub
"""

import os
import sys
import argparse
import subprocess
import json
from typing import Optional

# 添加项目根目录和 src 目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "src"))

from tool_registry import ToolDefinition

# 工具定义 - 供 tool_registry 动态加载
TOOL_DEFINITION = ToolDefinition(
    name="clawhub",
    description="与 ClawHub 公开技能注册表交互：搜索、安装、发布、更新 skills",
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "enum": ["search", "install", "update", "list", "publish", "login", "logout", "whoami"],
                "description": "操作命令"
            },
            "query": {"type": "string", "description": "搜索关键词 (用于 search)"},
            "slug": {"type": "string", "description": "Skill slug (用于 install/update/publish)"},
            "path": {"type": "string", "description": "Skill 路径 (用于 publish)"},
            "version": {"type": "string", "description": "指定版本号"},
            "all": {"type": "boolean", "description": "更新所有 skills"},
            "force": {"type": "boolean", "description": "强制覆盖"},
            "limit": {"type": "number", "description": "搜索结果数量限制"}
        },
        "required": ["command"]
    },
    section="external",
    profiles=["coding"]
)


def execute(args: dict) -> dict:
    """执行 clawhub 命令"""
    command = args.get("command", "")

    if command == "search":
        result = cmd_search(args.get("query", ""), args.get("limit", 10))
    elif command == "install":
        result = cmd_install(args.get("slug", ""), args.get("version"), args.get("force", False))
    elif command == "update":
        result = cmd_update(args.get("slug"), args.get("all", False), args.get("version"), args.get("force", False))
    elif command == "list":
        result = cmd_list()
    elif command == "publish":
        result = cmd_publish(args.get("path", ""), args.get("slug"), None, args.get("version"), None, None)
    elif command == "whoami":
        result = cmd_whoami()
    else:
        return {"success": False, "error": f"Unknown command: {command}"}

    # 转换为工具返回格式
    if result.get("success"):
        return {"success": True, "content": result.get("content", "")}
    else:
        return {"success": False, "error": result.get("error", "Unknown error")}


def run_clawhub(args_list: list, timeout: int = 60) -> dict:
    """运行 clawhub 命令"""
    try:
        result = subprocess.run(
            ["clawhub"] + args_list,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return {
            "success": result.returncode == 0,
            "content": result.stdout,
            "error": result.stderr if result.returncode != 0 else None
        }
    except FileNotFoundError:
        return {
            "success": False,
            "error": "clawhub 未安装。请运行: npm i -g clawhub"
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": f"命令执行超时 ({timeout}秒)"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def cmd_search(query: str, limit: int = 10) -> dict:
    """搜索 skills"""
    return run_clawhub(["search", query, "--limit", str(limit)])


def cmd_install(slug: str, version: str = None, force: bool = False) -> dict:
    """安装 skill"""
    args = ["install", slug]
    if version:
        args.extend(["--version", version])
    if force:
        args.append("--force")
    return run_clawhub(args)


def cmd_update(slug: str = None, all_skills: bool = False, version: str = None, force: bool = False) -> dict:
    """更新 skills"""
    if all_skills:
        args = ["update", "--all"]
    else:
        args = ["update", slug] if slug else ["update"]

    if version:
        args.extend(["--version", version])
    if force:
        args.append("--force")
    return run_clawhub(args)


def cmd_list() -> dict:
    """列出已安装的 skills"""
    return run_clawhub(["list"])


def cmd_publish(path: str, slug: str = None, name: str = None, version: str = None,
                 changelog: str = None, tags: str = None) -> dict:
    """发布 skill"""
    args = ["publish", path]
    if slug:
        args.extend(["--slug", slug])
    if name:
        args.extend(["--name", name])
    if version:
        args.extend(["--version", version])
    if changelog:
        args.extend(["--changelog", changelog])
    if tags:
        args.extend(["--tags", tags])
    return run_clawhub(args, timeout=120)


def cmd_login(token: str = None, label: str = "CLI token", no_browser: bool = False) -> dict:
    """登录 ClawHub"""
    args = ["login"]
    if token:
        args.extend(["--token", token])
    if label:
        args.extend(["--label", label])
    if no_browser:
        args.append("--no-browser")
    return run_clawhub(args)


def cmd_logout() -> dict:
    """登出 ClawHub"""
    return run_clawhub(["logout"])


def cmd_whoami() -> dict:
    """查看当前登录用户"""
    return run_clawhub(["whoami"])


def main():
    parser = argparse.ArgumentParser(
        description="ClawHub Tool - 与 ClawHub 公开技能注册表交互",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    # 搜索 skills
    python -m tools.clawhub search "python"

    # 安装 skill
    python -m tools.clawhub install my-skill

    # 列出已安装
    python -m tools.clawhub list

    # 更新所有
    python -m tools.clawhub update --all

    # 发布 skill
    python -m tools.clawhub publish ./my-skill --slug my-skill

    # 查看当前用户
    python -m tools.clawhub whoami
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # search
    search_parser = subparsers.add_parser("search", help="搜索 skills")
    search_parser.add_argument("query", help="搜索关键词")
    search_parser.add_argument("--limit", "-n", type=int, default=10, help="最大结果数")

    # install
    install_parser = subparsers.add_parser("install", help="安装 skill")
    install_parser.add_argument("slug", help="Skill slug")
    install_parser.add_argument("--version", "-v", help="指定版本")
    install_parser.add_argument("--force", "-f", action="store_true", help="强制覆盖")

    # update
    update_parser = subparsers.add_parser("update", help="更新 skills")
    update_parser.add_argument("slug", nargs="?", help="Skill slug")
    update_parser.add_argument("--all", "-a", action="store_true", help="更新所有")
    update_parser.add_argument("--version", "-v", help="指定版本")
    update_parser.add_argument("--force", "-f", action="store_true", help="强制覆盖")

    # list
    subparsers.add_parser("list", help="列出已安装的 skills")

    # publish
    publish_parser = subparsers.add_parser("publish", help="发布 skill")
    publish_parser.add_argument("path", help="Skill 路径")
    publish_parser.add_argument("--slug", help="Skill slug")
    publish_parser.add_argument("--name", help="显示名称")
    publish_parser.add_argument("--version", "-v", help="版本号")
    publish_parser.add_argument("--changelog", help="更新日志")
    publish_parser.add_argument("--tags", help="标签 (逗号分隔)")

    # login
    login_parser = subparsers.add_parser("login", help="登录 ClawHub")
    login_parser.add_argument("--token", help="API token")
    login_parser.add_argument("--label", default="CLI token", help="标签")
    login_parser.add_argument("--no-browser", action="store_true", help="不打开浏览器")

    # logout
    subparsers.add_parser("logout", help="登出 ClawHub")

    # whoami
    subparsers.add_parser("whoami", help="查看当前登录用户")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    result = None

    if args.command == "search":
        result = cmd_search(args.query, args.limit)
    elif args.command == "install":
        result = cmd_install(args.slug, args.version, args.force)
    elif args.command == "update":
        result = cmd_update(args.slug, args.all, args.version, args.force)
    elif args.command == "list":
        result = cmd_list()
    elif args.command == "publish":
        result = cmd_publish(args.path, args.slug, args.name, args.version, args.changelog, args.tags)
    elif args.command == "login":
        result = cmd_login(args.token, args.label, args.no_browser)
    elif args.command == "logout":
        result = cmd_logout()
    elif args.command == "whoami":
        result = cmd_whoami()

    if result:
        if result.get("success"):
            print(result.get("content", ""))
        else:
            print(f"错误: {result.get('error', '未知错误')}", file=sys.stderr)
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
