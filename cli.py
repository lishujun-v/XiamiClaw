#!/usr/bin/env python3
"""
OpenClaw CLI - 交互式命令行界面

用法:
    python cli.py                      # 交互模式（可切换 agent）
    python cli.py "用户消息"           # 使用默认 agent 单次执行
    python cli.py -a agent2 "消息"     # 使用指定 agent 单次执行
    python cli.py -i                   # 交互模式（等价于不带参数）
    python cli.py --list-agents        # 列出所有可用的 agent
"""

import os
import sys
import argparse
import yaml
import platform
from datetime import datetime

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


def supports_ansi() -> bool:
    """判断终端是否支持 ANSI 颜色"""
    return sys.stdout.isatty() and os.environ.get("TERM") not in (None, "", "dumb")


def color(text: str, code: str) -> str:
    """包装 ANSI 颜色"""
    if not supports_ansi():
        return text
    return f"\033[{code}m{text}\033[0m"


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


def print_welcome(current_agent_name: str = None):
    """打印欢迎信息"""
    print("=" * 60)
    print("  输入消息开始对话")
    print("  命令: /agent /skills /tools /prompt /new /clear /exit")
    if current_agent_name:
        print(f"  当前 Agent: {current_agent_name}")
    print("=" * 60)


def print_home_banner():
    """打印 CLI 首页欢迎 Logo 和提示语"""
    width = max(60, min(get_terminal_width(), 100))
    inner = width - 2
    title = " XiamiClaw CLI "
    subtitle = "多 Agent 协作终端"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    top = f"╭{'─' * inner}╮"
    mid = f"├{'─' * inner}┤"
    bot = f"╰{'─' * inner}╯"

    print(color(top, "36"))
    print(color(f"│{title.center(inner)}│", "1;36"))
    print(color(f"│{subtitle.center(inner)}│", "36"))
    print(color(mid, "36"))
    print(color(f"│ {'欢迎回来，准备开始任务。'.ljust(inner - 1)}│", "37"))
    print(color(f"│ {'常用命令: /agent  /skills  /tools  /new  /exit'.ljust(inner - 1)}│", "37"))
    print(color(f"│ {('启动时间: ' + now).ljust(inner - 1)}│", "90"))
    print(color(bot, "36"))


def _read_single_key():
    """读取单个按键，返回标准化键名"""
    # Windows
    if platform.system() == "Windows":
        import msvcrt
        ch = msvcrt.getch()
        if ch in (b"\x00", b"\xe0"):
            ch2 = msvcrt.getch()
            mapping = {
                b"H": "UP",
                b"P": "DOWN",
                b"K": "LEFT",
                b"M": "RIGHT",
            }
            return mapping.get(ch2, "")
        if ch == b"\r":
            return "ENTER"
        if ch == b"\x1b":
            return "ESC"
        return ""

    # POSIX
    import select
    import time
    import termios
    import tty

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch1 = os.read(fd, 1)
        if ch1 == b"\x1b":
            seq = b""
            deadline = time.time() + 0.25
            while time.time() < deadline:
                ready, _, _ = select.select([fd], [], [], 0.03)
                if not ready:
                    if seq:
                        break
                    continue
                seq += os.read(fd, 1)

                if len(seq) >= 2 and seq[0:1] in (b"[", b"O"):
                    break

            if len(seq) >= 2 and seq[0:1] in (b"[", b"O"):
                ch3 = seq[1:2]
                mapping = {
                    b"A": "UP",
                    b"B": "DOWN",
                    b"C": "RIGHT",
                    b"D": "LEFT",
                }
                return mapping.get(ch3, "")

            if seq.startswith(b"[") and len(seq) == 1:
                # 有些终端序列分片较慢，再尝试读一个字节
                ready, _, _ = select.select([fd], [], [], 0.08)
                if ready:
                    ch3 = os.read(fd, 1)
                    mapping = {
                        b"A": "UP",
                        b"B": "DOWN",
                        b"C": "RIGHT",
                        b"D": "LEFT",
                    }
                    return mapping.get(ch3, "")

            if not seq:
                return "ESC"
            return "ESC"
        if ch1 in (b"\r", b"\n"):
            return "ENTER"
        return ""
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def _render_agent_menu(names: list, selected: int, current_agent_name: str) -> int:
    """渲染 Agent 选择菜单，返回渲染的行数"""
    lines = [
        "=== Agent 选择 ===",
        "使用方向键选择 Agent，Enter 确认，Esc 取消",
        "",
    ]

    for idx, name in enumerate(names):
        current_marker = " (当前)" if name == current_agent_name else ""
        prefix = "> " if idx == selected else "  "
        lines.append(f"{prefix}{name}{current_marker}")

    for line in lines:
        print(f"\r\033[2K{line}")

    return len(lines)


def select_agent_with_arrows(agents: dict, current_agent_name: str):
    """
    使用方向键选择 agent

    Returns:
        选中的 agent 名称；如果取消则返回 None
    """
    names = list(agents.keys())
    if not names:
        return None

    try:
        selected = names.index(current_agent_name)
    except ValueError:
        selected = 0

    print("")
    rendered_lines = _render_agent_menu(names, selected, current_agent_name)
    while True:
        key = _read_single_key()
        if key in ("UP", "LEFT"):
            selected = (selected - 1) % len(names)
            print(f"\033[{rendered_lines}A", end="")
            rendered_lines = _render_agent_menu(names, selected, current_agent_name)
        elif key in ("DOWN", "RIGHT"):
            selected = (selected + 1) % len(names)
            print(f"\033[{rendered_lines}A", end="")
            rendered_lines = _render_agent_menu(names, selected, current_agent_name)
        elif key == "ENTER":
            return names[selected]
        elif key == "ESC":
            return None


def interactive_mode(agents: dict, current_agent_name: str, default_agent: str):
    """
    交互模式

    Args:
        agents: 所有 agent 的字典 {name: agent_instance}
        current_agent_name: 当前使用的 agent 名称
        default_agent: 默认 agent 名称
    """
    print_welcome(current_agent_name)

    # 检查 readline 库
    try:
        import readline
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

                if cmd == 'agent':
                    choice = select_agent_with_arrows(agents, current_agent_name)

                    if choice is None:
                        print("\n已取消切换 Agent")
                        continue

                    if choice in agents:
                        current_agent_name = choice
                        print(f"\n✓ 已切换到 Agent: {current_agent_name}")
                    continue

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
                    current_agent = agents[current_agent_name]
                    print("\n可用 Tools:")
                    for tool in current_agent.tool_registry.get_all_tools():
                        print(f"  - {tool.name}: {tool.description}")
                    continue

                if cmd == 'clear':
                    os.system('cls' if os.name == 'nt' else 'clear')
                    print_welcome(current_agent_name)
                    continue

                if cmd == 'prompt':
                    current_agent = agents[current_agent_name]
                    print("\n=== System Prompt ===")
                    print(current_agent.get_system_prompt())
                    print("...(truncated)")
                    continue

                if cmd == 'new':
                    # 创建新 session，清除历史对话
                    from sessions import get_session_manager
                    session_manager = get_session_manager()
                    new_session_id = session_manager.create_session(force_new=True)
                    print(f"\n✓ 已创建新 Session: {new_session_id}")
                    print("  下次对话将不携带历史记录")
                    continue

                # 未知命令
                print(f"未知命令: {cmd}")
                print("可用命令: /exit, /quit, /agent, /skills, /tools, /clear, /prompt, /new")
                continue

            # 检查不带斜杠的退出命令（兼容）
            if user_input.lower() in ['exit', 'quit', 'q']:
                print("Goodbye!")
                break

            # 执行请求 - 使用当前选中的 agent
            current_agent = agents[current_agent_name]
            response = current_agent.run(user_input)
            print(f"╭{'─' * (width - 2)}╮")
            print(f"    {response}")
            print(f"╰{'─' * (width - 2)}╯")

        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"\nError: {e}")

    return current_agent_name


def load_agents_config():
    """从配置文件加载 agents 配置"""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        return config.get('agents', {})
    except Exception as e:
        print(f"Warning: 加载配置文件失败: {e}")
        return {}


def get_all_agent_configs():
    """获取所有 agent 配置"""
    agents_config = load_agents_config()

    if not agents_config:
        # 如果没有配置，返回默认配置
        return [{
            "name": "agent1",
            "workspace": "./workspace",
            "description": "默认 agent"
        }]

    return agents_config.get('list', [])


def get_default_agent_name():
    """获取默认 agent 名称"""
    agents_config = load_agents_config()
    if not agents_config:
        return "agent1"
    return agents_config.get('default', 'agent1')


def list_available_agents():
    """列出所有可用的 agent"""
    agent_list = get_all_agent_configs()

    if not agent_list:
        print("  agent1 (默认)")
        return

    print("\n可用 Agents:")
    for agent_cfg in agent_list:
        name = agent_cfg.get('name', 'unknown')
        desc = agent_cfg.get('description', '')
        workspace = agent_cfg.get('workspace', '')
        print(f"  - {name}: {desc} (workspace: {workspace})")


def create_all_agents(confirm_dangerous_tools: bool = True):
    """
    创建所有配置的 agents

    Args:
        confirm_dangerous_tools: 是否在执行危险工具前确认

    Returns:
        (agents_dict, default_agent_name)
    """
    from master_agent import MasterAgent

    agent_list = get_all_agent_configs()
    agents = {}
    default_agent = get_default_agent_name()

    print(f"正在初始化 {len(agent_list)} 个 agents...")

    for agent_cfg in agent_list:
        name = agent_cfg.get('name', 'agent')
        workspace = agent_cfg.get('workspace', './workspace')
        agent = MasterAgent(
            max_iterations=20,
            confirm_dangerous_tools=confirm_dangerous_tools,
            workspace=workspace,
            agent_name=name,
        )
        agents[name] = agent

    print(f"已创建 {len(agents)} 个 agents")
    return agents, default_agent


def main():
    parser = argparse.ArgumentParser(description="OpenClaw Agent CLI")
    parser.add_argument('message', nargs='?', help='要处理的消息')
    parser.add_argument('-i', '--interactive', action='store_true', help='交互模式')
    parser.add_argument('-s', '--show-prompt', action='store_true', help='显示 System Prompt')
    parser.add_argument('--no-confirm', action='store_true', help='禁用危险工具执行前确认')
    parser.add_argument('-a', '--agent', type=str, default=None, help='选择要使用的 agent (如 agent1, agent2, agent3)')
    parser.add_argument('--list-agents', action='store_true', help='列出所有可用的 agent')

    args = parser.parse_args()
    print_home_banner()

    # 列出所有可用的 agent
    if args.list_agents:
        list_available_agents()
        return

    # 创建所有 agents
    confirm_dangerous = not args.no_confirm
    agents, default_agent = create_all_agents(confirm_dangerous_tools=confirm_dangerous)

    # 确定当前使用的 agent
    if args.agent and args.agent in agents:
        current_agent_name = args.agent
    else:
        current_agent_name = default_agent

    current_agent = agents[current_agent_name]

    print(f"\n=== 当前 Agent: {current_agent_name} ===")
    print(f"Workspace: {current_agent.workspace}")

    if args.show_prompt:
        print("\n=== System Prompt ===")
        print(current_agent.get_system_prompt())
        print("\n" + "=" * 60)

    if args.interactive or args.message is None:
        # 交互模式 - 传入所有 agents 和当前 agent
        interactive_mode(agents, current_agent_name, default_agent)
    else:
        # 单次执行 - 使用指定的 agent
        response = current_agent.run(args.message)
        print(f"\n{response}")


if __name__ == "__main__":
    main()
