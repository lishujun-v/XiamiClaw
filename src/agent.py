"""
Master Agent 核心逻辑
包含 ReAct 循环、任务分解、上下文管理等
"""

import os
import re
import json
from typing import Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum

from .tool_registry import ToolRegistry
from .skill_loader import SkillLoader, SkillEntry
from .subagent_runner import SubAgentRunner
from .executor import Executor, ExecutionResult


class AgentState(Enum):
    """Agent 状态"""
    IDLE = "idle"
    THINKING = "thinking"
    EXECUTING = "executing"
    WAITING = "waiting"
    DONE = "done"
    ERROR = "error"


@dataclass
class Message:
    """消息"""
    role: str  # user, assistant, tool, system
    content: str
    tool_call: Optional[dict] = None
    tool_call_id: Optional[str] = None


@dataclass
class Task:
    """任务"""
    description: str
    status: str = "pending"  # pending, in_progress, completed, failed
    subtasks: list["Task"] = field(default_factory=list)
    result: Any = None
    error: Optional[str] = None


class MasterAgent:
    """
    Master Agent - 主代理
    实现渐进式加载、ReAct 模式、任务分解等
    """

    def __init__(
        self,
        profile: str = "coding",
        llm_provider: Optional[Callable] = None
    ):
        self.profile = profile
        self.llm_provider = llm_provider

        # 组件
        self.tool_registry = ToolRegistry()
        self.skill_loader = SkillLoader()
        self.subagent_runner = SubAgentRunner()
        self.executor = Executor(self.tool_registry, self.subagent_runner)

        # 状态
        self.state = AgentState.IDLE
        self.messages: list[Message] = []
        self.current_task: Optional[Task] = None

        # 渐进式加载
        self._skills_loaded: set[str] = set()
        self._skill_contents: dict[str, str] = {}

        # 初始化
        self._init()

    def _init(self):
        """初始化"""
        # 加载所有 skills
        self.skill_loader.load_all()

        # 过滤可用 skills
        available_bins = self._detect_available_bins()
        self.available_skills = self.skill_loader.filter_by_bins(available_bins)

    def _detect_available_bins(self) -> list[str]:
        """检测可用的命令行工具"""
        import shutil

        bins = []
        # 需要检测的工具列表
        tools_to_check = [
            'git', 'gh', 'docker', 'npm', 'node', 'pytest', 'python',
            'python3', 'curl', 'rg', 'grep', 'find'
        ]

        for tool in tools_to_check:
            if shutil.which(tool):
                bins.append(tool)

        return bins

    def build_system_prompt(self) -> str:
        """构建系统提示词"""
        # 获取可用 tools
        tools = self.tool_registry.get_tools_for_profile(self.profile)
        tools_format = self.tool_registry.to_openai_format(tools)

        # 获取可用 skills
        snapshot = self.skill_loader.build_snapshot(self.available_skills)
        skills_prompt = self.skill_loader.format_skills_prompt(snapshot)

        # 子代理信息
        subagents_info = self.subagent_runner.format_agents_info()

        system_prompt = f"""You are Master Agent, an AI assistant that can help users accomplish various tasks.

## Available Tools
{json.dumps(tools_format, indent=2, ensure_ascii=False)}

## Skills
{skills_prompt}

## Sub Agents
{subagents_info}

## Instructions

1. **Progressive Loading**: When you need to use a skill, first read its SKILL.md file using the `read` tool to understand its usage.

2. **Tool Usage**: Use the appropriate tool to accomplish tasks. Tools include: read, write, edit, exec.

3. **Sub Agent Usage**: When a task requires specialized processing, you can call sub-agents from the subagents directory.

4. **ReAct Pattern**: Think step by step:
   - Think: Analyze the task and plan your approach
   - Action: Execute the appropriate tool or sub-agent
   - Observe: Check the result
   - Reflect: Adjust your approach if needed

5. **Task Decomposition**: For complex tasks, break them into subtasks and handle them one by one.

6. **Error Handling**: If an error occurs, try to recover and continue, or provide a helpful response to the user.

7. **Context Awareness**: Consider the conversation history and current state when making decisions.

When you need to use a skill, follow these steps:
1. Use the `read` tool to read the SKILL.md file of that skill
2. Understand the commands and usage from the file
3. Execute the appropriate commands using the `exec` tool
4. Process the results and provide your response

Now, please help the user with their request.
"""

        return system_prompt

    def call_llm(
        self,
        messages: list[dict],
        tools: list[dict] = None,
        **kwargs
    ) -> dict:
        """调用 LLM"""
        if self.llm_provider:
            return self.llm_provider(messages, tools, **kwargs)
        else:
            # 如果没有配置 LLM，使用模拟响应
            return self._mock_llm_response(messages)

    def _mock_llm_response(self, messages: list[dict]) -> dict:
        """模拟 LLM 响应（用于测试）"""
        last_message = messages[-1]["content"] if messages else ""

        # 简单响应
        return {
            "type": "text",
            "content": f"I understand your request: {last_message[:50]}... Please provide more details or let me know how I can help."
        }

    def load_skill(self, skill_name: str) -> Optional[str]:
        """渐进式加载 skill 内容"""
        if skill_name in self._skills_loaded:
            return self._skill_contents.get(skill_name)

        content = self.skill_loader.get_skill_content(skill_name)
        if content:
            self._skills_loaded.add(skill_name)
            self._skill_contents[skill_name] = content

        return content

    def execute_tool(self, tool_name: str, args: dict) -> ExecutionResult:
        """执行工具"""
        return self.executor.execute_tool(tool_name, args)

    def execute_subagent(
        self,
        agent_name: str,
        args: dict = None,
        timeout: int = 60
    ) -> ExecutionResult:
        """执行子代理"""
        return self.executor.execute_subagent(agent_name, args, timeout)

    def parse_tool_call(self, llm_response: dict) -> Optional[dict]:
        """解析 LLM 响应中的工具调用"""
        # OpenAI 格式
        if "tool_calls" in llm_response:
            for call in llm_response["tool_calls"]:
                return {
                    "name": call["function"]["name"],
                    "arguments": call["function"]["arguments"]
                }

        # 简单文本格式 - 尝试解析
        content = llm_response.get("content", "")
        if isinstance(content, str):
            # 检查是否是工具调用格式
            if content.strip().startswith("{"):
                try:
                    return json.loads(content)
                except:
                    pass

        return None

    def run(
        self,
        user_message: str,
        max_iterations: int = 10
    ) -> str:
        """
        运行 Agent 处理用户请求

        Args:
            user_message: 用户消息
            max_iterations: 最大迭代次数

        Returns:
            str: 最终响应
        """
        self.messages = [Message(role="system", content=self.build_system_prompt())]
        self.messages.append(Message(role="user", content=user_message))

        conversation = [
            {"role": "system", "content": self.build_system_prompt()},
            {"role": "user", "content": user_message}
        ]

        # 获取可用 tools
        tools = self.tool_registry.to_openai_format(
            self.tool_registry.get_tools_for_profile(self.profile)
        )

        for iteration in range(max_iterations):
            # 调用 LLM
            response = self.call_llm(conversation, tools=tools)

            # 检查是否是工具调用
            tool_call = self.parse_tool_call(response)

            if tool_call:
                tool_name = tool_call.get("name")
                tool_args = tool_call.get("arguments", {})

                # 如果 arguments 是字符串，尝试解析
                if isinstance(tool_args, str):
                    try:
                        tool_args = json.loads(tool_args)
                    except:
                        tool_args = {}

                # 检查是否是 sub-agent 调用
                if tool_name == "subagent":
                    agent_name = tool_args.get("agent")
                    agent_args = tool_args.get("args", {})
                    result = self.execute_subagent(agent_name, agent_args)
                else:
                    # 执行工具
                    result = self.execute_tool(tool_name, tool_args)

                # 构建结果消息
                result_content = result.content if result.success else result.error
                conversation.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": f"tool_{iteration}",
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": json.dumps(tool_args)
                        }
                    }]
                })
                conversation.append({
                    "role": "tool",
                    "tool_call_id": f"tool_{iteration}",
                    "content": result_content
                })

            else:
                # 文本响应
                content = response.get("content", "")
                conversation.append({
                    "role": "assistant",
                    "content": content
                })
                return content

        # 达到最大迭代次数
        return "我已尽最大努力处理您的请求，但尚未完成。您可以提供更多细节或重新描述您的问题。"

    def run_simple(self, user_message: str) -> str:
        """
        简单模式 - 不使用 LLM
        解析用户意图并直接执行
        """
        message_lower = user_message.lower()

        # 1. 检查是否需要读取 skill
        skill_pattern = r'(?:使用|调用|执行)\s*(\w+)\s*(?:skill|技能)'
        skill_match = re.search(skill_pattern, message_lower)
        if skill_match:
            skill_name = skill_match.group(1)
            content = self.load_skill(skill_name)
            if content:
                return f"## {skill_name} Skill\n\n{content}"

        # 2. 检查是否需要执行 sub-agent
        subagent_pattern = r'(?:调用|执行)\s*(\w+)\s*(?:sub[-_]?agent|子代理)'
        subagent_match = re.search(subagent_pattern, message_lower)
        if subagent_match:
            agent_name = subagent_match.group(1)
            result = self.execute_subagent(agent_name)
            if result.success:
                return result.content
            else:
                return f"Error: {result.error}"

        # 3. 检查是否需要读取文件
        read_pattern = r'读取?\s+(.+)'
        read_match = re.search(read_pattern, message_lower)
        if read_match:
            file_path = read_match.group(1).strip()
            result = self.execute_tool("read", {"file_path": file_path})
            if result.success:
                return result.content
            else:
                return f"Error: {result.error}"

        # 4. 检查是否需要执行命令
        exec_pattern = r'(?:执行|运行)\s+(.+)'
        exec_match = re.search(exec_pattern, message_lower)
        if exec_match:
            command = exec_match.group(1).strip()
            result = self.execute_tool("exec", {"command": command})
            if result.success:
                return result.content
            else:
                return f"Error: {result.error}"

        # 默认响应
        return f"""我收到了您的消息: {user_message}

当前可用功能:
- Skills: {', '.join(s.skill.name for s in self.available_skills)}
- Tools: read, write, edit, exec
- SubAgents: {', '.join(self.subagent_runner.get_available_agents())}

请告诉我您需要什么帮助?"""
