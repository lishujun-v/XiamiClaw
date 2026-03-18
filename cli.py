#!/usr/bin/env python3
"""
OpenClaw CLI - 交互式命令行界面

用法:
    python cli.py                      # 交互模式
    python cli.py "用户消息"           # 单次执行
    python cli.py -i                   # 交互模式（等价于不带参数）
"""

import os
import sys
import argparse

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 尝试导入 prompt_toolkit，支持中文输入
try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.input.default import create_input
    from prompt_toolkit.keys import Keys
    USE_PROMPT_TOOLKIT = True
except ImportError:
    USE_PROMPT_TOOLKIT = False


def create_llm_provider():
    """创建 LLM 提供函数"""
    from utils.llm_req import call_llm

    def llm_provider(messages, tools=None, **kwargs):
        return call_llm(messages=messages, tools=tools)
    return llm_provider


def print_welcome():
    """打印欢迎信息"""
    print("=" * 60)
    print("  OpenClaw Agent - CLI Mode")
    print("=" * 60)
    print("  输入消息开始对话")
    print("  输入 'exit' 或 'quit' 退出")
    print("  输入 'skills' 查看可用技能")
    print("  输入 'tools' 查看可用工具")
    print("  输入 'clear' 清屏")
    print("=" * 60)


def interactive_mode(agent):
    """交互模式"""
    print_welcome()

    if USE_PROMPT_TOOLKIT:
        # 使用 prompt_toolkit，支持中文
        session = PromptSession(
            "\n> ",
            multiline=False,
            enable_history_search=True,
        )
    else:
        print("\n提示: 安装 prompt_toolkit 可获得更好的中文支持: pip install prompt_toolkit")

    while True:
        try:
            print("*" * 40)
            if USE_PROMPT_TOOLKIT:
                user_input = session.prompt().strip()
            else:
                user_input = input("\nYOU >： ").strip()

            if not user_input:
                continue

            if user_input.lower() in ['exit', 'quit', 'q']:
                print("Goodbye!")
                break

            if user_input.lower() == 'skills':
                from src.skill_loader import SkillLoader
                loader = SkillLoader()
                loader.load_all()
                print("\n可用 Skills:")
                for skill in loader.get_all_skills():
                    name = skill.skill.name if hasattr(skill, 'skill') else 'unknown'
                    desc = skill.skill.description if hasattr(skill, 'skill') else ''
                    print(f"  - {name}: {desc}")
                continue

            if user_input.lower() == 'tools':
                print("\n可用 Tools:")
                for tool in agent.tool_registry.get_all_tools():
                    print(f"  - {tool.name}: {tool.description}")
                continue

            if user_input.lower() == 'clear':
                os.system('cls' if os.name == 'nt' else 'clear')
                print_welcome()
                continue

            if user_input.lower() == 'prompt':
                print("\n=== System Prompt ===")
                print(agent.get_system_prompt())
                print("...(truncated)")
                continue

            # 执行请求
            response = agent.run(user_input)
            print(f"\nXiaMi > ： {response}\n")

        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"\nError: {e}")


def main():
    parser = argparse.ArgumentParser(description="OpenClaw Agent CLI")
    parser.add_argument('message', nargs='?', help='要处理的消息')
    parser.add_argument('-i', '--interactive', action='store_true', help='交互模式')
    parser.add_argument('-s', '--show-prompt', action='store_true', help='显示 System Prompt')

    args = parser.parse_args()

    # 导入组件
    from master_agent import MasterAgent

    # 创建 Agent
    print("Initializing OpenClaw Agent...")
    agent = MasterAgent()
    agent.print_welcome()

    if args.show_prompt:
        print("\n=== System Prompt ===")
        print(agent.get_system_prompt())
        print("\n" + "=" * 60)

    if args.interactive or args.message is None:
        # 交互模式
        interactive_mode(agent)
    else:
        # 单次执行
        response = agent.run(args.message)
        print(f"\n{response}")


if __name__ == "__main__":
    main()
