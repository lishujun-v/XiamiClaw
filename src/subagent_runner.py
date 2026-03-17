"""
子代理运行器 - 管理执行 Sub Agents
"""

import os
import sys
import subprocess
import json
from typing import Optional, Any
from dataclasses import dataclass


@dataclass
class SubAgentResult:
    """子代理执行结果"""
    success: bool
    output: str = ""
    error: Optional[str] = None


class SubAgentRunner:
    """子代理运行器"""

    def __init__(self, subagents_dir: str = "subagents"):
        self.subagents_dir = subagents_dir
        self._discovered_agents: dict[str, str] = {}
        self._discover_agents()

    def _discover_agents(self):
        """发现可用的子代理"""
        if not os.path.exists(self.subagents_dir):
            return

        for item in os.listdir(self.subagents_dir):
            if item.endswith('.py') and not item.startswith('_'):
                agent_name = item[:-3]  # 去掉 .py 后缀
                self._discovered_agents[agent_name] = os.path.join(
                    self.subagents_dir, item
                )

    def get_available_agents(self) -> list[str]:
        """获取可用子代理列表"""
        return list(self._discovered_agents.keys())

    def has_agent(self, agent_name: str) -> bool:
        """检查子代理是否存在"""
        return agent_name in self._discovered_agents

    def execute(
        self,
        agent_name: str,
        args: list[str] = None,
        timeout: int = 60
    ) -> SubAgentResult:
        """
        执行子代理

        Args:
            agent_name: 子代理名称
            args: 命令行参数
            timeout: 超时时间(秒)

        Returns:
            SubAgentResult: 执行结果
        """
        if agent_name not in self._discovered_agents:
            return SubAgentResult(
                success=False,
                error=f"Unknown sub-agent: {agent_name}"
            )

        script_path = self._discovered_agents[agent_name]

        # 构建命令
        cmd = [sys.executable, script_path]
        if args:
            cmd.extend(args)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=os.getcwd()
            )

            if result.returncode == 0:
                return SubAgentResult(
                    success=True,
                    output=result.stdout
                )
            else:
                return SubAgentResult(
                    success=False,
                    output=result.stdout,
                    error=result.stderr or f"Exit code: {result.returncode}"
                )

        except subprocess.TimeoutExpired:
            return SubAgentResult(
                success=False,
                error=f"Sub-agent timeout ({timeout}s)"
            )
        except Exception as e:
            return SubAgentResult(
                success=False,
                error=f"Sub-agent error: {str(e)}"
            )

    def execute_with_kwargs(
        self,
        agent_name: str,
        timeout: int = 60,
        **kwargs
    ) -> SubAgentResult:
        """
        使用关键字参数执行子代理

        Args:
            agent_name: 子代理名称
            timeout: 超时时间(秒)
            **kwargs: 传给子代理的参数

        Returns:
            SubAgentResult: 执行结果
        """
        args = []
        for key, value in kwargs.items():
            # 转换为 --key value 格式
            args.append(f"--{key}")
            if value is not None:
                args.append(str(value))

        return self.execute(agent_name, args, timeout)

    def format_agents_info(self) -> str:
        """格式化子代理信息"""
        if not self._discovered_agents:
            return "No sub-agents available."

        lines = ["<available_sub_agents>"]
        for name, path in sorted(self._discovered_agents.items()):
            lines.append(f"  <sub_agent>")
            lines.append(f"    <name>{name}</name>")
            lines.append(f"    <path>{path}</path>")
            lines.append(f"  </sub_agent>")
        lines.append("</available_sub_agents>")
        return "\n".join(lines)
