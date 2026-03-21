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

# 设置 UTF-8 编码
os.environ['PYTHONIOENCODING'] = 'utf-8'

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 获取终端宽度
def get_terminal_width():
    try:
        return os.get_terminal_size().columns
    except:
        return 60


# Unicode 框线字符
def print_input_box(prompt=">", width=None):
    """打印输入框上线，用户输入后会打印下线"""
    if width is None:
        width = get_terminal_width()

    # 使用 Unicode 框线字符
    print(f"╭{'─' * (width - 2)}╮")
    print(f"│ {prompt} ", end="")


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
    print("  输入 '/exit' 或 '/quit' 退出")
    print("  输入 '/skills' 查看可用技能")
    print("  输入 '/tools' 查看可用工具")
    print("  输入 '/clear' 清屏")
    print("  输入 '/prompt' 查看系统提示")
    print("  输入 '/session' 创建新 session（清除历史）")
    print("=" * 60)


def interactive_mode(agent):
    """交互模式"""
    print_welcome()

    # 检查 readline 库
    try:
        import readline
        # macOS 上可以安装 gnureadline 获得更好的中文支持
        # 或者直接用系统自带的 readline
    except ImportError:
        pass

    while True:
        try:
            # 打印输入框上线
            width = get_terminal_width()
            print(f"╭{'─' * (width - 2)}╮")
            print(f"│ ", end="")

            # 用户输入
            user_input = input("> ").strip()

            # 打印输入框下线
            print(f"╰{'─' * (width - 2)}╯")

            if not user_input:
                continue

            # 检查斜杠命令
            if user_input.startswith('/'):
                cmd = user_input[1:].lower()

                if cmd in ['exit', 'quit', 'q']:
                    print("Goodbye!")
                    break

                if cmd == 'skills':
                    from src.skill_loader import SkillLoader
                    loader = SkillLoader()
                    loader.load_all()
                    print("\n可用 Skills:")
                    for skill in loader.get_all_skills():
                        name = skill.skill.name if hasattr(skill, 'skill') else 'unknown'
                        desc = skill.skill.description if hasattr(skill, 'skill') else ''
                        print(f"  - {name}: {desc}")
                    continue

                if cmd == 'tools':
                    print("\n可用 Tools:")
                    for tool in agent.tool_registry.get_all_tools():
                        print(f"  - {tool.name}: {tool.description}")
                    continue

                if cmd == 'clear':
                    os.system('cls' if os.name == 'nt' else 'clear')
                    print_welcome()
                    continue

                if cmd == 'prompt':
                    print("\n=== System Prompt ===")
                    print(agent.get_system_prompt())
                    print("...(truncated)")
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
            print(f"╭{'─' * (width - 2)}╮")
            print(f"    {response}")
            print(f"╰{'─' * (width - 2)}╯")

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
    parser.add_argument('--no-confirm', action='store_true', help='禁用危险工具执行前确认')

    args = parser.parse_args()

    # 导入组件
    from master_agent import MasterAgent

    # 创建 Agent
    print("Initializing OpenClaw Agent...")
    agent = MasterAgent(
        max_iterations=20,
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
    else:
        # 单次执行
        response = agent.run(args.message)
        print(f"\n{response}")


if __name__ == "__main__":
    main()
