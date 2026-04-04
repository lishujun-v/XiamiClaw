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
import unicodedata
from datetime import datetime

# 设置 UTF-8 编码
os.environ['PYTHONIOENCODING'] = 'utf-8'

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.agentic_loop import EventType


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


def _char_display_width(ch: str) -> int:
    """按终端显示宽度计算单个字符的占位。"""
    if unicodedata.combining(ch):
        return 0
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return 2
    return 1


def _display_width(text: str) -> int:
    """计算字符串在终端中的显示宽度。"""
    return sum(_char_display_width(ch) for ch in text)


def _fit_display_width(text: str, width: int) -> str:
    """截断字符串，使其显示宽度不超过目标宽度。"""
    if width <= 0:
        return ""

    parts = []
    current = 0
    for ch in text:
        ch_width = _char_display_width(ch)
        if current + ch_width > width:
            break
        parts.append(ch)
        current += ch_width
    return "".join(parts)


def _pad_display_width(text: str, width: int, align: str = "left") -> str:
    """将字符串补齐到目标显示宽度。"""
    fitted = _fit_display_width(text, width)
    padding = max(0, width - _display_width(fitted))

    if align == "center":
        left = padding // 2
        right = padding - left
        return f"{' ' * left}{fitted}{' ' * right}"
    if align == "right":
        return f"{' ' * padding}{fitted}"
    return f"{fitted}{' ' * padding}"


def _wrap_display_width(text: str, width: int) -> list[str]:
    """按终端显示宽度分行，避免中文内容把边框顶歪。"""
    if width <= 0:
        return [""]
    if not text:
        return [""]

    lines = []
    current = []
    current_width = 0

    for ch in text:
        ch_width = _char_display_width(ch)
        if current and current_width + ch_width > width:
            lines.append("".join(current))
            current = [ch]
            current_width = ch_width
            continue

        current.append(ch)
        current_width += ch_width

    if current:
        lines.append("".join(current))

    return lines


def _box_title(width: int, title: str) -> str:
    """生成带标题的框线，避免输入框和回复框视觉混淆。"""
    inner = max(0, width - 2)
    label = f" {title} "
    label = _fit_display_width(label, inner)
    label_width = _display_width(label)
    if label_width >= inner:
        return label
    left = (inner - label_width) // 2
    right = inner - label_width - left
    return f"{'─' * left}{label}{'─' * right}"


# Unicode 框线字符
def print_input_box(prompt=">", width=None):
    """打印输入框上线，用户输入后会打印下线"""
    if width is None:
        width = get_terminal_width()

    print(color(f"╭{_box_title(width, '你的输入')}╮", "36"))
    print(color("│", "36"), end="")
    if prompt:
        print(f" {prompt} ", end="")


def create_llm_provider():
    """创建 LLM 提供函数"""
    from utils.llm_req import call_llm

    def llm_provider(messages, tools=None, **kwargs):
        return call_llm(messages=messages, tools=tools)
    return llm_provider


def print_welcome(current_agent_name: str = None, workspace: str = None, max_iterations: int = None):
    """打印欢迎信息"""
    line = "=" * 60
    print(color(line, "36"))
    print(color("  会话已就绪，输入消息开始对话", "1;32"))
    if current_agent_name:
        parts = [f"Agent: {color(current_agent_name, '1;96')}"]
        if workspace:
            parts.append(f"Workspace: {color(workspace, '96')}")
        if max_iterations is not None:
            parts.append(f"最大迭代: {color(str(max_iterations), '1;96')}")
        print("  " + " | ".join(parts))
    print(color("  命令: /agent /skills /tools /prompt /new /clear /exit", "33"))
    print(color(line, "36"))


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
    print(color(f"│{_pad_display_width(title, inner, 'center')}│", "1;36"))
    print(color(f"│{_pad_display_width(subtitle, inner, 'center')}│", "36"))
    print(color(mid, "36"))
    print(color(f"│ {_pad_display_width('欢迎回来，准备开始任务。', inner - 1)}│", "32"))
    print(color(f"│ {_pad_display_width('输入 /agent 切换 Agent，输入 /exit 退出。', inner - 1)}│", "33"))
    print(color(f"│ {_pad_display_width('启动时间: ' + now, inner - 1)}│", "90"))
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


def print_response_box(content: str, width: int):
    """以稳定的多行格式渲染回复框，避免重复换行和框线错位"""
    if content is None:
        return

    normalized = str(content).replace('\r\n', '\n').rstrip()
    if not normalized:
        normalized = "(空回复)"

    inner_width = max(10, width - 4)
    lines = []
    for raw_line in normalized.split('\n'):
        wrapped = _wrap_display_width(raw_line, inner_width)
        if wrapped:
            lines.extend(wrapped)
        else:
            lines.append("")

    print(color(f"╭{_box_title(width, '助手回复')}╮", "32"))
    for line in lines:
        print(f"{color('│', '32')} {_pad_display_width(line, inner_width)} {color('│', '32')}")
    print(color(f"╰{'─' * (width - 2)}╯", "32"))


def _clear_inline_status(stream_state: dict):
    """清理单行状态提示，避免后续输出错位。"""
    if stream_state.get("inline_status"):
        print("\r\033[2K", end="", flush=True)
        stream_state["inline_status"] = False


def _stream_chunk_has_visible_text(chunk: str) -> bool:
    """判断流式 chunk 是否包含可见文本，避免空白 chunk 打开回复框。"""
    if not isinstance(chunk, str):
        return bool(chunk)
    return bool(chunk.strip())


def _ensure_response_box_open(stream_state: dict, width: int):
    """按需打开回复框，并输出此前缓存的前导空白。"""
    if stream_state["open"]:
        return

    print(color(f"╭{_box_title(width, '助手回复')}╮", "32"))
    print(f"{color('│', '32')} ", end='', flush=True)
    stream_state["open"] = True
    stream_state["had_stream"] = True

    pending_chunks = stream_state.get("pending_stream_chunks", [])
    if pending_chunks:
        print("".join(pending_chunks), end='', flush=True)
        stream_state["pending_stream_chunks"] = []


def handle_event(event, stream_state: dict, width: int):
    """根据事件类型处理"""
    from src.agentic_loop import EventType

    if event.type == EventType.THINKING_START:
        _clear_inline_status(stream_state)
        print(f"\n{color('🤔 思考中...', '1;34')}")
    elif event.type == EventType.THINKING_PROGRESS:
        elapsed = event.data.get('elapsed', 0) if isinstance(event.data, dict) else 0
        last = stream_state.get("last_thinking_progress", 0.0)
        if elapsed - last >= 5.0:
            stream_state["last_thinking_progress"] = elapsed
            print(f"\r\033[2K{color(f'… 仍在思考中 ({elapsed:.1f}s)', '2;34')}", end="", flush=True)
            stream_state["inline_status"] = True
    elif event.type == EventType.TOOL_CALL:
        _clear_inline_status(stream_state)
        tool_name = event.data['name']
        args = event.data['args']
        print(f"\n{color(f'⚡ 正在调用工具: {tool_name}', '1;33')}")
        if args:
            import json
            args_str = json.dumps(args, indent=2, ensure_ascii=False)
            if len(args_str) > 500:
                args_str = args_str[:500] + "\n  ...(内容过长)"
            print(f"{color(args_str, '2')}")
    elif event.type == EventType.TOOL_PROGRESS:
        tool_name = event.data.get('name', 'unknown') if isinstance(event.data, dict) else 'unknown'
        elapsed = event.data.get('elapsed', 0) if isinstance(event.data, dict) else 0
        last = stream_state.get("last_tool_progress", 0.0)
        if elapsed - last >= 3.0:
            stream_state["last_tool_progress"] = elapsed
            print(f"\r\033[2K{color(f'… 工具 {tool_name} 执行中 ({elapsed:.1f}s)', '2;33')}", end="", flush=True)
            stream_state["inline_status"] = True
    elif event.type == EventType.TOOL_RESULT:
        _clear_inline_status(stream_state)
        success = event.data['success']
        content = event.data['content']
        error = event.data.get('error')
        if success:
            print(f"{color('✓ 工具执行成功', '32')}")
            display_content = content[:1000] if content else ""
            if len(content or "") > 1000:
                display_content += "\n...(内容过长)"
            if display_content:
                print(f"\n{color(display_content, '2')}")
        else:
            print(f"{color('✗ 工具执行失败', '31')}")
            if error:
                print(f"{color(error, '31')}")
    elif event.type == EventType.STREAM_CHUNK:
        _clear_inline_status(stream_state)
        chunk = event.data if isinstance(event.data, str) else str(event.data or "")
        if not stream_state["open"]:
            if _stream_chunk_has_visible_text(chunk):
                _ensure_response_box_open(stream_state, width)
            else:
                stream_state.setdefault("pending_stream_chunks", []).append(chunk)
                return
        print(chunk, end='', flush=True)
    elif event.type == EventType.STREAM_END:
        _clear_inline_status(stream_state)
        if stream_state["open"]:
            print()  # 换行
            print(color(f"╰{'─' * (width - 2)}╯", "32"))
            stream_state["open"] = False
        else:
            stream_state["pending_stream_chunks"] = []
    elif event.type == EventType.ITERATION_START:
        _clear_inline_status(stream_state)
        data = event.data or {}
        current = data.get("iteration")
        total = data.get("max_iterations")
        if current and total:
            print(color(f"\n▶ 迭代 {current}/{total}", "2;36"))
    elif event.type == EventType.ITERATION_END:
        # 迭代结束，不显示详细信息
        pass
    elif event.type == EventType.ERROR:
        _clear_inline_status(stream_state)
        print(f"\n{color(f'错误: {event.data}', '31')}")
    elif event.type == EventType.FINAL_RESPONSE:
        # FINAL_RESPONSE 事件只在非流式模式下由外层处理
        pass


def interactive_mode(agents: dict, current_agent_name: str, default_agent: str):
    """
    交互模式

    Args:
        agents: 所有 agent 的字典 {name: agent_instance}
        current_agent_name: 当前使用的 agent 名称
        default_agent: 默认 agent 名称
        stream_callback: 流式回调函数，用于实时打印 LLM 输出
    """
    current_agent = agents.get(current_agent_name)
    current_agent.logger.info("CLI entered interactive mode | agent=%s default_agent=%s", current_agent_name, default_agent)
    print_welcome(
        current_agent_name=current_agent_name,
        workspace=getattr(current_agent, "workspace", None),
        max_iterations=getattr(current_agent, "max_iterations", None),
    )

    # 检查 readline 库
    if sys.stdin.isatty() and sys.stdout.isatty():
        try:
            import readline
        except ImportError:
            pass

    while True:
        try:
            width = get_terminal_width()
            print_input_box(prompt="", width=width)

            # 用户输入
            user_input = input("> ").strip()

            print(color(f"╰{'─' * (width - 2)}╯", "36"))

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
                        agents[current_agent_name].logger.info("CLI switched current agent to %s", current_agent_name)
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
                    current_agent = agents.get(current_agent_name)
                    print_welcome(
                        current_agent_name=current_agent_name,
                        workspace=getattr(current_agent, "workspace", None),
                        max_iterations=getattr(current_agent, "max_iterations", None),
                    )
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
            current_agent.logger.info("CLI dispatching interactive message | length=%s", len(user_input))

            # 使用事件流方式执行
            stream_state = {"open": False, "had_stream": False, "pending_stream_chunks": []}
            final_response = None

            for event in current_agent.run_stream(user_input):
                if event.type == EventType.FINAL_RESPONSE:
                    final_response = event.data
                else:
                    handle_event(event, stream_state, width)

            # 如果没有任何流式输出，使用 FINAL_RESPONSE 显示
            if not stream_state["had_stream"] and final_response is not None:
                print_response_box(final_response, width)
            elif not stream_state["had_stream"] and final_response is None:
                print(color("本轮执行已结束，但没有返回可显示内容。", "33"))

        except KeyboardInterrupt:
            current_agent = agents.get(current_agent_name)
            if current_agent:
                current_agent.logger.info("CLI interactive mode interrupted by user")
            print("\n\nGoodbye!")
            break
        except Exception as e:
            current_agent = agents.get(current_agent_name)
            if current_agent:
                current_agent.logger.exception("CLI interactive mode error")
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


def create_all_agents(confirm_dangerous_tools: bool = True, max_iterations: int = 20):
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

    print(color(f"初始化 agents: {len(agent_list)} 个", "36"))

    for agent_cfg in agent_list:
        name = agent_cfg.get('name', 'agent')
        workspace = agent_cfg.get('workspace', './workspace')
        agent = MasterAgent(
            max_iterations=max_iterations,
            confirm_dangerous_tools=confirm_dangerous_tools,
            workspace=workspace,
            agent_name=name,
        )
        agents[name] = agent
        agent.logger.info("CLI created agent instance | workspace=%s", workspace)

    print(color(f"agents 就绪: {len(agents)} 个", "32"))
    return agents, default_agent


def main():
    parser = argparse.ArgumentParser(description="OpenClaw Agent CLI")
    parser.add_argument('message', nargs='?', help='要处理的消息')
    parser.add_argument('-i', '--interactive', action='store_true', help='交互模式')
    parser.add_argument('-s', '--show-prompt', action='store_true', help='显示 System Prompt')
    parser.add_argument('--no-confirm', action='store_true', help='禁用危险工具执行前确认')
    parser.add_argument('-a', '--agent', type=str, default=None, help='选择要使用的 agent (如 agent1, agent2, agent3)')
    parser.add_argument('--list-agents', action='store_true', help='列出所有可用的 agent')
    parser.add_argument('--stream', action='store_true', help='强制开启流式输出')
    parser.add_argument('--max-iterations', type=int, default=50, help='最大迭代次数（默认 50）')

    args = parser.parse_args()
    print_home_banner()

    # 列出所有可用的 agent
    if args.list_agents:
        list_available_agents()
        return

    # 创建所有 agents
    confirm_dangerous = not args.no_confirm
    agents, default_agent = create_all_agents(
        confirm_dangerous_tools=confirm_dangerous,
        max_iterations=args.max_iterations,
    )

    # 确定当前使用的 agent
    if args.agent and args.agent in agents:
        current_agent_name = args.agent
    else:
        current_agent_name = default_agent

    current_agent = agents[current_agent_name]
    current_agent.logger.info(
        "CLI started | interactive=%s show_prompt=%s message_present=%s",
        args.interactive or args.message is None,
        args.show_prompt,
        bool(args.message),
    )

    if not (args.interactive or args.message is None):
        print(color(f"\n当前 Agent: {current_agent_name}", "1;96"))
        print(color(f"Workspace: {current_agent.workspace}", "96"))
        print(color(f"最大迭代次数: {current_agent.max_iterations}", "36"))

    if args.show_prompt:
        print("\n=== System Prompt ===")
        print(current_agent.get_system_prompt())
        print("\n" + "=" * 60)
        if not args.interactive and args.message is None:
            return

    # 检查是否启用流式输出
    stream_callback = None
    if args.stream:
        # 通过命令行 --stream 参数强制开启
        def stream_callback(chunk):
            print(chunk, end='', flush=True)
    else:
        # 检查 config.yaml 中的配置
        try:
            config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            custom_config = config.get('custom', {})
            if custom_config.get('stream', False):
                def stream_callback(chunk):
                    print(chunk, end='', flush=True)
        except:
            pass

    if args.interactive or args.message is None:
        # 交互模式 - 传入所有 agents 和当前 agent
        interactive_mode(agents, current_agent_name, default_agent)
    else:
        # 单次执行 - 使用指定的 agent
        current_agent.logger.info("CLI dispatching single message | length=%s", len(args.message or ""))
        width = get_terminal_width()
        stream_state = {"open": False, "had_stream": False, "pending_stream_chunks": []}
        final_response = None

        for event in current_agent.run_stream(args.message):
            if event.type == EventType.FINAL_RESPONSE:
                final_response = event.data
            else:
                handle_event(event, stream_state, width)

        # 如果没有任何流式输出，使用 FINAL_RESPONSE 显示
        if not stream_state["had_stream"] and final_response is not None:
            print_response_box(final_response, width)
        elif not stream_state["had_stream"] and final_response is None:
            print(color("本轮执行已结束，但没有返回可显示内容。", "33"))


if __name__ == "__main__":
    main()
