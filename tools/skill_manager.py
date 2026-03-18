#!/usr/bin/env python3
"""
Skill Manager Tool - 管理本地 Skills

功能：
- 列出所有已安装的 skills
- 显示 skill 详情
- 加载 skill 到上下文
- 验证 skill 格式
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path
from typing import Optional, List, Dict
import re

# 添加项目根目录和 src 目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "src"))

from tool_registry import ToolDefinition
from tool_registry import ToolDefinition

# 工具定义 - 供 tool_registry 动态加载
TOOL_DEFINITION = ToolDefinition(
    name="skill_manager",
    description="管理本地 Skills：列出、查看详情、验证格式",
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "enum": ["list", "detail", "validate"],
                "description": "操作命令"
            },
            "name": {"type": "string", "description": "Skill 名称"},
            "path": {"type": "string", "description": "Skill 路径"},
            "dir": {"type": "string", "description": "Skills 目录路径"}
        },
        "required": ["command"]
    },
    section="external",
    profiles=["coding"]
)


def execute(args: dict) -> dict:
    """执行 skill_manager 命令"""
    command = args.get("command", "")

    # 直接使用参数
    try:
        if command == "list":
            # 创建一个类似 argparse.Namespace 的对象
            class Args:
                pass
            exec_args = Args()
            exec_args.dir = args.get("dir")
            result = cmd_list(exec_args)
        elif command == "detail":
            class Args:
                pass
            exec_args = Args()
            exec_args.name = args.get("name")
            exec_args.path = args.get("path")
            result = cmd_detail(exec_args)
        elif command == "validate":
            class Args:
                pass
            exec_args = Args()
            exec_args.name = args.get("name")
            exec_args.path = args.get("path")
            result = cmd_validate(exec_args)
        else:
            return {"success": False, "error": f"Unknown command: {command}"}

        if result.get("success"):
            return {"success": True, "content": result.get("content", "")}
        else:
            return {"success": False, "error": result.get("content", "Unknown error")}

    except Exception as e:
        return {"success": False, "error": str(e)}


def get_skills_dir() -> Path:
    """获取 skills 目录"""
    # 当前工作目录下的 skills 文件夹
    return Path.cwd() / "skills"


def list_skills(skills_dir: Path = None) -> List[Dict]:
    """列出所有 skills"""
    if skills_dir is None:
        skills_dir = get_skills_dir()

    if not skills_dir.exists():
        return []

    skills = []
    for item in skills_dir.iterdir():
        if item.is_dir():
            skill_file = item / "SKILL.md"
            if skill_file.exists():
                skill_info = parse_skill_file(skill_file)
                skill_info["path"] = str(item.relative_to(skills_dir))
                skill_info["name"] = item.name
                skills.append(skill_info)
            else:
                skills.append({
                    "name": item.name,
                    "path": str(item.relative_to(skills_dir)),
                    "description": "(无 SKILL.md)"
                })

    return skills


def parse_skill_file(skill_file: Path) -> Dict:
    """解析 SKILL.md 文件"""
    content = skill_file.read_text(encoding="utf-8")

    # 解析 YAML frontmatter
    info = {
        "name": skill_file.parent.name,
        "description": "",
        "emoji": None,
        "metadata": {}
    }

    # 提取 frontmatter
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            frontmatter = parts[1].strip()
            # 解析简单的 key: value 格式
            for line in frontmatter.split("\n"):
                line = line.strip()
                if ":" in line:
                    key, value = line.split(":", 1)
                    key = key.strip()
                    value = value.strip()

                    if key == "name":
                        info["name"] = value
                    elif key == "description":
                        info["description"] = value
                    elif key == "emoji":
                        info["emoji"] = value
                    elif key == "metadata":
                        # 尝试解析 JSON
                        try:
                            import json
                            info["metadata"] = json.loads(value)
                        except:
                            info["metadata"] = {"raw": value}

    # 如果没有从 frontmatter 获取描述，尝试从第一行获取
    if not info["description"]:
        lines = content.split("\n")
        for line in lines:
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("---"):
                info["description"] = line[:100]
                break

    return info


def get_skill_detail(name: str = None, path: str = None) -> Dict:
    """获取 skill 详情"""
    skills_dir = get_skills_dir()

    if path:
        skill_path = skills_dir / path
    elif name:
        skill_path = skills_dir / name
    else:
        return {"error": "请提供 skill name 或 path"}

    skill_file = skill_path / "SKILL.md"

    if not skill_file.exists():
        return {"error": f"Skill 不存在: {skill_path}"}

    content = skill_file.read_text(encoding="utf-8")

    return {
        "name": skill_path.name,
        "path": str(skill_path.relative_to(skills_dir)),
        "content": content,
        "files": [str(f.relative_to(skill_path)) for f in skill_path.rglob("*") if f.is_file()]
    }


def validate_skill(name: str = None, path: str = None) -> Dict:
    """验证 skill 格式"""
    skills_dir = get_skills_dir()

    if path:
        skill_path = skills_dir / path
    elif name:
        skill_path = skills_dir / name
    else:
        return {"valid": False, "errors": ["请提供 skill name 或 path"]}

    errors = []
    warnings = []

    # 检查目录是否存在
    if not skill_path.exists():
        return {"valid": False, "errors": [f"Skill 目录不存在: {skill_path}"]}

    # 检查 SKILL.md 是否存在
    skill_file = skill_path / "SKILL.md"
    if not skill_file.exists():
        errors.append("缺少 SKILL.md 文件")

    # 检查 frontmatter
    if skill_file.exists():
        content = skill_file.read_text(encoding="utf-8")

        if not content.startswith("---"):
            warnings.append("SKILL.md 缺少 YAML frontmatter")

        # 检查必需字段
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = parts[1].strip()
                if "name:" not in frontmatter:
                    errors.append("frontmatter 缺少 name 字段")
                if "description:" not in frontmatter:
                    warnings.append("frontmatter 缺少 description 字段")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "path": str(skill_path.relative_to(skills_dir))
    }


def cmd_list(args) -> dict:
    """列出所有 skills"""
    skills_dir = Path(args.dir) if args.dir else get_skills_dir()

    if not skills_dir.exists():
        return {
            "success": True,
            "content": f"Skills 目录不存在: {skills_dir}\n请先创建 skills 目录或指定目录"
        }

    skills = list_skills(skills_dir)

    if not skills:
        return {
            "success": True,
            "content": f"目录 {skills_dir} 中没有找到 skills"
        }

    lines = [f"# 已安装的 Skills (共 {len(skills)} 个)", ""]

    for skill in skills:
        emoji = skill.get("emoji", "")
        name = skill.get("name", "unknown")
        desc = skill.get("description", "")
        path = skill.get("path", "")

        lines.append(f"## {emoji} {name}".strip())
        if desc:
            lines.append(f"   {desc}")
        lines.append(f"   路径: {path}")
        lines.append("")

    return {"success": True, "content": "\n".join(lines)}


def cmd_detail(args) -> dict:
    """显示 skill 详情"""
    detail = get_skill_detail(args.name, args.path)

    if "error" in detail:
        return {"success": False, "content": detail["error"]}

    lines = [
        f"# Skill: {detail['name']}",
        f"路径: {detail['path']}",
        "",
        "## 文件列表",
    ]

    for f in detail.get("files", []):
        lines.append(f"- {f}")

    lines.extend(["", "## SKILL.md 内容", "", detail.get("content", "")])

    return {"success": True, "content": "\n".join(lines)}


def cmd_validate(args) -> dict:
    """验证 skill"""
    result = validate_skill(args.name, args.path)

    lines = [f"# 验证结果: {result.get('path', 'unknown')}"]

    if result.get("valid"):
        lines.append("✅ 验证通过")
    else:
        lines.append("❌ 验证失败")

    if result.get("errors"):
        lines.append("")
        lines.append("## 错误")
        for e in result["errors"]:
            lines.append(f"- ❌ {e}")

    if result.get("warnings"):
        lines.append("")
        lines.append("## 警告")
        for w in result["warnings"]:
            lines.append(f"- ⚠️ {w}")

    return {"success": result.get("valid", False), "content": "\n".join(lines)}


def main():
    parser = argparse.ArgumentParser(
        description="Skill Manager - 管理本地 Skills",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    # 列出所有 skills
    python -m tools.skill_manager list

    # 指定目录
    python -m tools.skill_manager list --dir ./my-skills

    # 查看 skill 详情
    python -m tools.skill_manager detail --name report_writer

    # 验证 skill 格式
    python -m tools.skill_manager validate --name report_writer
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # list
    list_parser = subparsers.add_parser("list", help="列出所有 skills")
    list_parser.add_argument("--dir", "-d", help="Skills 目录路径")

    # detail
    detail_parser = subparsers.add_parser("detail", help="显示 skill 详情")
    detail_parser.add_argument("--name", "-n", help="Skill 名称")
    detail_parser.add_argument("--path", "-p", help="Skill 路径")

    # validate
    validate_parser = subparsers.add_parser("validate", help="验证 skill 格式")
    validate_parser.add_argument("--name", "-n", help="Skill 名称")
    validate_parser.add_argument("--path", "-p", help="Skill 路径")

    args = parser.parse_args()

    if not args.command:
        # 默认列出
        args.command = "list"
        args.dir = None

    result = None

    if args.command == "list":
        result = cmd_list(args)
    elif args.command == "detail":
        result = cmd_detail(args)
    elif args.command == "validate":
        result = cmd_validate(args)

    if result:
        if result.get("success"):
            print(result.get("content", ""))
        else:
            print(f"错误: {result.get('content', '未知错误')}", file=sys.stderr)
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
