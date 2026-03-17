"""
Master Agent - 主 Agent 入口

负责：
1. 初始化各组件（LLM、工具注册表、Skill加载器、Memory管理）
2. 构建 System Prompt
3. 执行 Agentic Loop
"""

import os
import sys
from typing import Any, Callable, Optional

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.agentic_loop import AgenticLoop
from src.tool_registry import ToolRegistry
from src.skill_loader import SkillLoader
from memory import get_memory_manager
from sessions import get_session_manager
from utils.llm_req import call_llm


class MasterAgent:
    """Master Agent 主类"""

    def __init__(
        self,
        llm_provider: Optional[Callable] = None,
        tool_registry: Optional[ToolRegistry] = None,
        skill_loader: Optional[SkillLoader] = None,
        max_iterations: int = 10,
        show_progress: bool = True,
    ):
        """
        初始化 Master Agent

        Args:
            llm_provider: LLM 提供函数，默认使用 call_llm
            tool_registry: 工具注册表
            skill_loader: Skill 加载器
            max_iterations: 最大迭代次数
            show_progress: 是否显示执行进度
        """
        # 默认 LLM 提供者
        if llm_provider is None:
            llm_provider = self._default_llm_provider

        self.llm_provider = llm_provider
        self.show_progress = show_progress
        self.max_iterations = max_iterations

        # 初始化组件
        self.tool_registry = tool_registry or self._create_tool_registry()
        self.skill_loader = skill_loader or self._create_skill_loader()
        self.memory_manager = get_memory_manager()
        self.session_manager = get_session_manager()

        # 创建 Agentic Loop
        self.loop = AgenticLoop(
            llm_provider=self.llm_provider,
            tool_registry=self.tool_registry,
            skill_loader=self.skill_loader,
            max_iterations=max_iterations,
        )

    def _default_llm_provider(self, messages, tools=None, **kwargs):
        """默认 LLM 提供者"""
        return call_llm(messages=messages, tools=tools)

    def _create_tool_registry(self) -> ToolRegistry:
        """创建工具注册表"""
        return ToolRegistry()

    def _create_skill_loader(self) -> SkillLoader:
        """创建 Skill 加载器"""
        loader = SkillLoader()
        loader.load_all()
        return loader

    def run(self, user_message: str) -> str:
        """
        运行 Agent 处理用户消息

        Args:
            user_message: 用户消息

        Returns:
            Agent 的最终回复
        """
        return self.loop.run(user_message, show_progress=self.show_progress)

    def get_system_prompt(self) -> str:
        """获取当前 System Prompt"""
        return self.loop._build_system_prompt()

    def print_welcome(self):
        """打印欢迎信息"""
        print("=" * 50)
        print("  OpenClaw Agent 初始化完成")
        print("=" * 50)
        print(f"  可用 Tools: {len(self.tool_registry.get_all_tools())}")
        print(f"  可用 Skills: {len(self.skill_loader.get_all_skills())}")
        print(f"  最大迭代次数: {self.max_iterations}")
        print("=" * 50)

    def list_skills(self):
        """列出所有可用技能"""
        skills = self.skill_loader.get_all_skills()
        print("\n可用 Skills:")
        for skill in skills:
            name = skill.skill.name if hasattr(skill, 'skill') else 'unknown'
            desc = skill.skill.description if hasattr(skill, 'skill') else ''
            print(f"  - {name}: {desc}")

    def list_tools(self):
        """列出所有可用工具"""
        tools = self.tool_registry.get_all_tools()
        print("\n可用 Tools:")
        for tool in tools:
            print(f"  - {tool.name}: {tool.description}")


def create_agent(
    max_iterations: int = 10,
    show_progress: bool = True,
) -> MasterAgent:
    """
    创建 Master Agent 的便捷函数

    Args:
        max_iterations: 最大迭代次数
        show_progress: 是否显示进度

    Returns:
        MasterAgent 实例
    """
    return MasterAgent(
        max_iterations=max_iterations,
        show_progress=show_progress,
    )


def interactive_mode(agent: MasterAgent):
    """交互模式"""
    print("=" * 60)
    print("  OpenClaw Agent - Interactive Mode")
    print("=" * 60)
    print("  输入消息开始对话")
    print("  输入 'exit' 或 'quit' 退出")
    print("  输入 'skills' 查看可用技能")
    print("  输入 'tools' 查看可用工具")
    print("  输入 'prompt' 查看系统提示")
    print("=" * 60)

    while True:
        try:
            user_input = input("\n> ").strip()

            if not user_input:
                continue

            if user_input.lower() in ['exit', 'quit', 'q']:
                print("Goodbye!")
                break

            if user_input.lower() == 'skills':
                agent.list_skills()
                continue

            if user_input.lower() == 'tools':
                agent.list_tools()
                continue

            if user_input.lower() == 'prompt':
                print("\n=== System Prompt ===")
                print(agent.get_system_prompt()[:2000])
                print("...(truncated)")
                continue

            # 执行请求
            response = agent.run(user_input)
            print(f"\n{response}")

        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"\nError: {e}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="OpenClaw Master Agent")
    parser.add_argument('message', nargs='?', help='要处理的消息')
    parser.add_argument('-i', '--interactive', action='store_true', help='交互模式')
    parser.add_argument('-s', '--show-prompt', action='store_true', help='显示 System Prompt')
    parser.add_argument('--max-iterations', type=int, default=10, help='最大迭代次数')

    args = parser.parse_args()

    # 创建 Agent
    print("Initializing OpenClaw Agent...")
    agent = create_agent(max_iterations=args.max_iterations)
    agent.print_welcome()

    if args.show_prompt:
        print("\n=== System Prompt ===")
        print(agent.get_system_prompt())
        print("\n" + "=" * 60)

    if args.interactive or args.message is None:
        # 交互模式
        interactive_mode(agent)
    elif args.message:
        # 单次执行
        response = agent.run(args.message)
        print(f"\n{response}")


if __name__ == "__main__":
    main()
