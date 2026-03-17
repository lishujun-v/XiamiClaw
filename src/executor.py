"""
执行器 - 协调 Tool 和 SubAgent 执行
"""

import json
import re
from typing import Optional, Any
from dataclasses import dataclass

from .tool_registry import ToolRegistry, ToolResult
from .subagent_runner import SubAgentRunner, SubAgentResult


@dataclass
class ExecutionResult:
    """执行结果"""
    success: bool
    tool_name: str = ""
    content: Any = None
    error: Optional[str] = None


class Executor:
    """执行器 - 协调工具和子代理的执行"""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        subagent_runner: SubAgentRunner
    ):
        self.tool_registry = tool_registry
        self.subagent_runner = subagent_runner
        self.execution_history: list[ExecutionResult] = []

    def execute_tool(self, tool_name: str, args: dict) -> ExecutionResult:
        """执行工具"""
        result = self.tool_registry.execute(tool_name, args)

        execution = ExecutionResult(
            success=result.success,
            tool_name=tool_name,
            content=result.content,
            error=result.error
        )
        self.execution_history.append(execution)

        return execution

    def execute_subagent(
        self,
        agent_name: str,
        args: dict = None,
        timeout: int = 60
    ) -> ExecutionResult:
        """执行子代理"""
        if args is None:
            args = {}

        result = self.subagent_runner.execute_with_kwargs(
            agent_name,
            timeout=timeout,
            **args
        )

        execution = ExecutionResult(
            success=result.success,
            tool_name=f"subagent:{agent_name}",
            content=result.output,
            error=result.error
        )
        self.execution_history.append(execution)

        return execution

    def can_handle(self, action: str) -> bool:
        """检查是否可以处理该动作"""
        # 检查是否是工具
        if self.tool_registry.get_tool(action):
            return True

        # 检查是否是子代理
        if self.subagent_runner.has_agent(action):
            return True

        return False

    def get_execution_summary(self) -> str:
        """获取执行历史摘要"""
        if not self.execution_history:
            return "No executions yet."

        lines = ["Execution History:"]
        for i, exec in enumerate(self.execution_history, 1):
            status = "✓" if exec.success else "✗"
            lines.append(
                f"  {i}. {status} {exec.tool_name}: "
                f"{exec.content[:50] if exec.content else exec.error}"
            )
        return "\n".join(lines)

    def clear_history(self):
        """清除执行历史"""
        self.execution_history = []
