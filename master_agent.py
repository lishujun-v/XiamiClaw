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
from memory import MemoryManager
from sessions import SessionManager
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
        confirm_dangerous_tools: bool = True,
        workspace: str = "./workspace",
        agent_name: str = "agent",
    ):
        """
        初始化 Master Agent

        Args:
            llm_provider: LLM 提供函数，默认使用 call_llm
            tool_registry: 工具注册表
            skill_loader: Skill 加载器
            max_iterations: 最大迭代次数
            show_progress: 是否显示执行进度
            confirm_dangerous_tools: 是否在执行危险工具前确认 (默认 True)
            workspace: 工作目录路径 (默认 "./workspace")
            agent_name: Agent 名称 (默认 "agent")
        """
        # 默认 LLM 提供者
        if llm_provider is None:
            llm_provider = self._default_llm_provider

        self.llm_provider = llm_provider
        self.show_progress = show_progress
        self.max_iterations = max_iterations
        self.confirm_dangerous_tools = confirm_dangerous_tools
        self.workspace = workspace
        self.agent_name = agent_name

        # 初始化组件
        self.tool_registry = tool_registry or self._create_tool_registry()
        self.skill_loader = skill_loader or self._create_skill_loader(workspace)

        # 创建独立的 Memory 和 Session 管理器（基于 workspace）
        memory_dir = os.path.join(workspace, "memory")
        sessions_dir = os.path.join(workspace, "sessions")

        self.memory_manager = MemoryManager(memory_dir)
        self.memory_manager._ensure_memory_dir()  # 确保 memory 目录存在

        self.session_manager = SessionManager(sessions_dir)  # SessionManager 会在初始化时创建目录

        # 创建 Agentic Loop
        self.loop = AgenticLoop(
            llm_provider=self.llm_provider,
            tool_registry=self.tool_registry,
            skill_loader=self.skill_loader,
            max_iterations=max_iterations,
            confirm_dangerous_tools=confirm_dangerous_tools,
            workspace=workspace,
            agent_name=agent_name,
            memory_manager=self.memory_manager,
            session_manager=self.session_manager,
        )

    def _default_llm_provider(self, messages, tools=None, **kwargs):
        """默认 LLM 提供者"""
        return call_llm(messages=messages, tools=tools)

    def _create_tool_registry(self) -> ToolRegistry:
        """创建工具注册表"""
        return ToolRegistry()

    def _create_skill_loader(self, workspace: str = "./workspace") -> SkillLoader:
        """创建 Skill 加载器"""
        # 每个 agent 有自己的 skills 目录
        skills_dir = os.path.join(workspace, "skills")
        loader = SkillLoader(skills_dir=skills_dir)
        loader.load_all()
        return loader

    def run(self, user_message: str, stream_callback=None) -> str:
        """
        运行 Agent 处理用户消息

        Args:
            user_message: 用户消息
            stream_callback: 流式回调函数，用于实时打印 LLM 输出

        Returns:
            Agent 的最终回复
        """
        return self.loop.run(user_message, show_progress=self.show_progress, stream_callback=stream_callback)

    def run_stream(self, user_message: str, show_progress: bool = True):
        """
        运行 Agent 处理用户消息 (生成器版本)

        Args:
            user_message: 用户消息
            show_progress: 是否显示进度

        Returns:
            生成器 yield 事件
        """
        yield from self.loop.run_stream(user_message, show_progress=show_progress)

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
    confirm_dangerous_tools: bool = True,
    workspace: str = "./workspace",
    agent_name: str = "agent",
) -> MasterAgent:
    """
    创建 Master Agent 的便捷函数

    Args:
        max_iterations: 最大迭代次数
        show_progress: 是否显示进度
        confirm_dangerous_tools: 是否在执行危险工具前确认 (默认 True)
        workspace: 工作目录路径 (默认 "./workspace")
        agent_name: Agent 名称 (默认 "agent")

    Returns:
        MasterAgent 实例
    """
    return MasterAgent(
        max_iterations=max_iterations,
        show_progress=show_progress,
        confirm_dangerous_tools=confirm_dangerous_tools,
        workspace=workspace,
        agent_name=agent_name,
    )


def interactive_mode(agent: MasterAgent):
    """交互模式"""
    print("=" * 60)
    print("  OpenClaw Agent - Interactive Mode")
    print("=" * 60)
    print("  输入消息开始对话")
    print("  输入 '/exit' 或 '/quit' 退出")
    print("  输入 '/skills' 查看可用技能")
    print("  输入 '/tools' 查看可用工具")
    print("  输入 '/prompt' 查看系统提示")
    print("  输入 '/clear' 清屏")
    print("  输入 '/session' 创建新 session（清除历史）")
    print("=" * 60)

    while True:
        try:
            user_input = input("\n> ").strip()

            if not user_input:
                continue

            # 检查斜杠命令
            if user_input.startswith('/'):
                cmd = user_input[1:].lower()

                if cmd in ['exit', 'quit', 'q']:
                    print("Goodbye!")
                    break

                if cmd == 'skills':
                    agent.list_skills()
                    continue

                if cmd == 'tools':
                    agent.list_tools()
                    continue

                if cmd == 'prompt':
                    print("\n=== System Prompt ===")
                    print(agent.get_system_prompt()[:2000])
                    print("...(truncated)")
                    continue

                if cmd == 'clear':
                    import os
                    os.system('cls' if os.name == 'nt' else 'clear')
                    print("=" * 60)
                    print("  OpenClaw Agent - Interactive Mode")
                    print("=" * 60)
                    continue

                if cmd == 'session':
                    # 创建新 session，清除历史对话
                    from sessions import get_session_manager
                    session_manager = get_session_manager()
                    new_session_id = session_manager.create_session(force_new=True)
                    print(f"\n✓ 已创建新 Session: {new_session_id}")
                    print("  下次对话将不携带历史记录")
                    continue

                # 未知命令
                print(f"未知命令: {cmd}")
                print("可用命令: /exit, /quit, /skills, /tools, /clear, /prompt, /session")
                continue

            # 检查不带斜杠的退出命令（兼容）
            if user_input.lower() in ['exit', 'quit', 'q']:
                print("Goodbye!")
                break

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
    parser.add_argument('--no-confirm', action='store_true', help='禁用危险工具执行前确认')

    args = parser.parse_args()

    # 创建 Agent
    print("Initializing OpenClaw Agent...")
    agent = create_agent(
        max_iterations=args.max_iterations,
        confirm_dangerous_tools=not args.no_confirm
    )
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
