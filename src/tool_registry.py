"""
工具注册表 - 管理所有可用工具
"""

import os
import sys
import json
import importlib.util
from typing import Any, Callable, Optional
from dataclasses import dataclass, field


@dataclass
class ToolDefinition:
    """工具定义"""
    name: str
    description: str
    parameters: dict
    section: str
    profiles: list[str] = field(default_factory=lambda: ["coding"])


@dataclass
class ToolResult:
    """工具执行结果"""
    success: bool
    content: Any = None
    error: Optional[str] = None


class ToolRegistry:
    """工具注册中心"""

    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}
        self._executors: dict[str, Callable] = {}
        self._register_builtin_tools()

    def _get_tools_dir(self) -> str:
        """获取 tools 目录路径"""
        # 从项目根目录查找 tools 目录
        current_file = os.path.abspath(__file__)
        # src/tool_registry.py -> 项目根目录/tools
        project_root = os.path.dirname(os.path.dirname(current_file))
        tools_dir = os.path.join(project_root, "tools")
        return tools_dir

    def _register_tools_from_directory(self):
        """从 tools 目录动态加载工具"""
        tools_dir = self._get_tools_dir()

        if not os.path.exists(tools_dir):
            return

        # 添加 tools 目录到 Python 路径
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)

        for filename in os.listdir(tools_dir):
            if filename.endswith(".py") and not filename.startswith("_"):
                module_name = filename[:-3]  # 去掉 .py 后缀
                tool_name = module_name  # 工具名就是文件名

                # 跳过已注册的内置工具
                if tool_name in self._tools:
                    continue

                try:
                    # 动态导入模块
                    spec = importlib.util.spec_from_file_location(module_name, os.path.join(tools_dir, filename))
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)

                        # 检查模块是否导出工具定义和执行函数
                        if hasattr(module, "TOOL_DEFINITION") and hasattr(module, "execute"):
                            tool_def = module.TOOL_DEFINITION
                            # 使用模块的文件名作为工具名
                            tool_def.name = tool_name
                            self.register(tool_def, module.execute)
                            print(f"Loaded tool: {tool_name}")
                except Exception as e:
                    print(f"Failed to load tool {tool_name}: {e}")

    def _register_builtin_tools(self):
        """注册内置工具"""
        # 先从 tools 目录加载工具
        self._register_tools_from_directory()
        # Core Tools
        self.register(
            ToolDefinition(
                name="read",
                description="Read file contents",
                parameters={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "limit": {"type": "number"},
                        "offset": {"type": "number"}
                    },
                    "required": ["file_path"]
                },
                section="fs",
                profiles=["coding"]
            ),
            self._execute_read
        )

        self.register(
            ToolDefinition(
                name="write",
                description="Create or overwrite files",
                parameters={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "content": {"type": "string"}
                    },
                    "required": ["file_path", "content"]
                },
                section="fs",
                profiles=["coding"]
            ),
            self._execute_write
        )

        self.register(
            ToolDefinition(
                name="edit",
                description="Make precise edits to files",
                parameters={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "old_string": {"type": "string"},
                        "new_string": {"type": "string"},
                        "replace_all": {"type": "boolean"}
                    },
                    "required": ["file_path", "old_string", "new_string"]
                },
                section="fs",
                profiles=["coding"]
            ),
            self._execute_edit
        )

        self.register(
            ToolDefinition(
                name="exec",
                description="Run shell commands",
                parameters={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                        "timeout": {"type": "number"},
                        "background": {"type": "boolean"}
                    },
                    "required": ["command"]
                },
                section="runtime",
                profiles=["coding"]
            ),
            self._execute_exec
        )

    def register(self, definition: ToolDefinition, executor: Callable):
        """注册工具"""
        self._tools[definition.name] = definition
        self._executors[definition.name] = executor

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """获取工具定义"""
        return self._tools.get(name)

    def get_all_tools(self) -> list[ToolDefinition]:
        """获取所有工具"""
        return list(self._tools.values())

    def get_tools_for_profile(self, profile: str) -> list[ToolDefinition]:
        """获取指定 profile 的工具"""
        return [
            t for t in self._tools.values()
            if not t.profiles or profile in t.profiles
        ]

    def execute(self, tool_name: str, args: dict) -> ToolResult:
        """执行工具"""
        executor = self._executors.get(tool_name)
        if not executor:
            return ToolResult(
                success=False,
                error=f"Unknown tool: {tool_name}"
            )

        try:
            result = executor(args)
            # 如果返回的是 dict，转换为 ToolResult
            if isinstance(result, dict):
                return ToolResult(
                    success=result.get("success", False),
                    content=result.get("content"),
                    error=result.get("error")
                )
            return result
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Tool execution error: {str(e)}"
            )

    def to_openai_format(self, tools: list[ToolDefinition]) -> list[dict]:
        """转换为 OpenAI 格式"""
        result = []
        for tool in tools:
            result.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters
                }
            })
        return result

    # ========== 内置工具实现 ==========

    def _execute_read(self, args: dict) -> ToolResult:
        """读取文件"""
        file_path = args.get("file_path", "")
        limit = args.get("limit")
        offset = args.get("offset")

        try:
            if not os.path.exists(file_path):
                return ToolResult(success=False, error=f"File not found: {file_path}")

            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            if offset:
                lines = lines[offset - 1:]
            if limit:
                lines = lines[:limit]

            content = ''.join(lines)
            return ToolResult(success=True, content=content)

        except Exception as e:
            return ToolResult(success=False, error=f"Read error: {str(e)}")

    def _execute_write(self, args: dict) -> ToolResult:
        """写入文件"""
        file_path = args.get("file_path", "")
        content = args.get("content", "")

        try:
            parent_dir = os.path.dirname(file_path)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)

            return ToolResult(
                success=True,
                content=f"Written {len(content)} chars to {file_path}"
            )

        except Exception as e:
            return ToolResult(success=False, error=f"Write error: {str(e)}")

    def _execute_edit(self, args: dict) -> ToolResult:
        """编辑文件"""
        file_path = args.get("file_path", "")
        old_string = args.get("old_string", "")
        new_string = args.get("new_string", "")
        replace_all = args.get("replace_all", False)

        try:
            if not os.path.exists(file_path):
                return ToolResult(success=False, error=f"File not found: {file_path}")

            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            if old_string not in content:
                return ToolResult(success=False, error="String not found in file")

            if replace_all:
                new_content = content.replace(old_string, new_string)
                count = content.count(old_string)
            else:
                new_content = content.replace(old_string, new_string, 1)
                count = 1

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)

            return ToolResult(
                success=True,
                content=f"Replaced {count} occurrence(s) in {file_path}"
            )

        except Exception as e:
            return ToolResult(success=False, error=f"Edit error: {str(e)}")

    def _execute_exec(self, args: dict) -> ToolResult:
        """执行命令"""
        import subprocess

        command = args.get("command", "")
        timeout = args.get("timeout", 300)
        background = args.get("background", False)

        try:
            if background:
                process = subprocess.Popen(
                    command,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                return ToolResult(
                    success=True,
                    content=f"Command started in background, PID: {process.pid}"
                )

            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )

            output = result.stdout
            if result.stderr:
                output = f"{output}\n{result.stderr}" if output else result.stderr

            if result.returncode == 0:
                return ToolResult(success=True, content=output or "Success")
            else:
                return ToolResult(
                    success=False,
                    error=f"Command failed (exit code: {result.returncode})\n{output}",
                    content=output
                )

        except subprocess.TimeoutExpired:
            return ToolResult(success=False, error=f"Command timeout ({timeout}s)")
        except Exception as e:
            return ToolResult(success=False, error=f"Exec error: {str(e)}")
