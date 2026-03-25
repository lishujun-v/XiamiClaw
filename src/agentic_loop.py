"""
Agentic Loop 模块

实现 ReAct 模式的 Agent 循环：
1. 渐进式加载 skill
2. 根据指导调用 tool
3. 执行 tool
4. 拼接结果到提示
5. 重复直到无 tool 可用
6. 返回最终回复

参考 OpenClaw 的实现方案
"""

import json
import re
import time
import threading
from queue import Empty, Queue
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Generator, Optional

# 导入 memory 模块
from memory import (
    # format_memory_context,
    get_memory_manager,
)
from sessions import (
    get_session_manager,
    # create_session,
    # add_user_message,
    # add_assistant_message,
    # add_tool_result,
    # format_conversation_for_llm,
)


class EventType(Enum):
    ITERATION_START = "iteration_start"
    THINKING_START = "thinking_start"
    THINKING_PROGRESS = "thinking_progress"
    STREAM_CHUNK = "stream_chunk"
    STREAM_END = "stream_end"
    TOOL_CALL = "tool_call"
    TOOL_PROGRESS = "tool_progress"
    TOOL_RESULT = "tool_result"
    ITERATION_END = "iteration_end"
    FINAL_RESPONSE = "final_response"
    ERROR = "error"


@dataclass
class Event:
    type: EventType
    data: Any


class Colors:
    """终端颜色"""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # 前景色
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # 背景色
    BG_BLACK = "\033[40m"
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"
    BG_MAGENTA = "\033[45m"
    BG_CYAN = "\033[46m"


@dataclass
class ToolCall:
    """工具调用"""
    name: str
    arguments: dict
    call_id: str


@dataclass
class LoopState:
    """循环状态"""
    iteration: int = 0
    tool_calls: int = 0
    start_time: float = field(default_factory=time.time)
    tool_history: list[dict] = field(default_factory=list)


class AgenticLoop:
    """
    Agentic Loop 实现

    特性：
    - 渐进式 skill 加载
    - ReAct 模式执行
    - 友好的交互提示
    - 循环检测
    - Memory 集成
    """

    def __init__(
        self,
        llm_provider: Optional[Callable] = None,
        tool_registry: Optional[Any] = None,
        skill_loader: Optional[Any] = None,
        max_iterations: int = 10,
        max_tool_calls_per_iteration: int = 5,
        enable_loop_detection: bool = True,
        loop_warning_threshold: int = 3,
        loop_max_threshold: int = 5,
        confirm_dangerous_tools: bool = True,
        workspace: str = "./workspace",
        agent_name: str = "agent",
        memory_manager: Any = None,
        session_manager: Any = None,
    ):
        """
        初始化 Agentic Loop

        Args:
            llm_provider: LLM 提供者函数
            tool_registry: 工具注册表
            skill_loader: Skill 加载器
            max_iterations: 最大迭代次数
            max_tool_calls_per_iteration: 每次迭代最大工具调用数
            enable_loop_detection: 启用循环检测
            loop_warning_threshold: 循环警告阈值
            loop_max_threshold: 循环最大阈值
            workspace: 工作目录路径 (默认 "./workspace")
            agent_name: Agent 名称 (默认 "agent")
            memory_manager: 传入的 Memory 管理器实例（可选）
            session_manager: 传入的 Session 管理器实例（可选）
        """
        self.llm_provider = llm_provider
        self.tool_registry = tool_registry
        self.skill_loader = skill_loader

        # Memory 管理器 - 如果传入则使用传入的，否则使用全局的
        if memory_manager is not None:
            self.memory_manager = memory_manager
        else:
            self.memory_manager = get_memory_manager()

        # Session 管理器 - 如果传入则使用传入的，否则使用全局的
        if session_manager is not None:
            self.session_manager = session_manager
        else:
            self.session_manager = get_session_manager()

        self.max_iterations = max_iterations
        self.max_tool_calls_per_iteration = max_tool_calls_per_iteration
        self.enable_loop_detection = enable_loop_detection
        self.loop_warning_threshold = loop_warning_threshold
        self.loop_max_threshold = loop_max_threshold
        self.confirm_dangerous_tools = confirm_dangerous_tools
        self.workspace = workspace
        self.agent_name = agent_name

        # 危险工具列表
        self._dangerous_tools = {"exec", "write", "edit"}

        # 状态
        self.state = LoopState()
        self.messages: list[dict] = []
        self.skills_loaded: dict[str, str] = {}

    def _print_header(self, text: str):
        """打印标题"""
        print(f"{Colors.CYAN}{Colors.BOLD}━" * 40)
        print(f"  {text}")
        print("━" * 40 + Colors.RESET)

    def _print_tool_call(self, tool_name: str, args: dict):
        """打印工具调用提示"""
        print(f"\n{Colors.YELLOW}{Colors.BOLD}⚡ 正在调用工具: {tool_name}{Colors.RESET}")
        if args:
            args_str = json.dumps(args, indent=2, ensure_ascii=False)
            # 限制显示长度
            if len(args_str) > 500:
                args_str = args_str[:500] + "\n  ...(内容过长)"
            print(f"{Colors.DIM}{args_str}{Colors.RESET}")

    def _print_tool_result(self, success: bool, content: str, error: str = None):
        """打印工具执行结果"""
        if success:
            print(f"{Colors.GREEN}✓ 工具执行成功{Colors.RESET}")
            # 限制显示长度
            display_content = content[:1000] if content else ""
            if len(content or "") > 1000:
                display_content += "\n...(内容过长)"
            if display_content:
                print(f"\n{Colors.DIM}{display_content}{Colors.RESET}")
        else:
            print(f"{Colors.RED}✗ 工具执行失败{Colors.RESET}")
            if error:
                print(f"{Colors.RED}{error}{Colors.RESET}")

    def _print_skill_load(self, skill_name: str):
        """打印 skill 加载提示"""
        print(f"\n{Colors.MAGENTA}{Colors.BOLD}📚 加载 Skill: {skill_name}{Colors.RESET}")

    def _print_thinking(self, thought: str = None):
        """打印思考提示"""
        print(f"\n{Colors.BLUE}{Colors.BOLD}🤔 思考中...{Colors.RESET}")
        if thought:
            display = thought[:300] + "..." if len(thought) > 300 else thought
            print(f"{Colors.DIM}{display}{Colors.RESET}")

    def _print_iteration(self, iteration: int, total: int):
        """打印迭代信息"""
        elapsed = time.time() - self.state.start_time
        print(f"\n{Colors.CYAN}▶ 迭代 {iteration + 1}/{total} | "
              f"工具调用: {self.state.tool_calls} | "
              f"耗时: {elapsed:.1f}s{Colors.RESET}")

    def _print_final_response(self, content: str):
        """打印最终响应"""
        print(f"\n{Colors.GREEN}{Colors.BOLD}" + "=" * 40)
        print("  最终响应")
        print("=" * 40 + Colors.RESET)
        # print(f"\n{content}\n")

    def _print_loop_warning(self, tool_name: str, count: int):
        """打印循环警告"""
        print(f"\n{Colors.RED}{Colors.BOLD}⚠️  循环检测警告:{Colors.RESET}")
        print(f"{Colors.RED}工具 `{tool_name}` 已被连续调用 {count} 次，"
              f"可能陷入循环。{Colors.RESET}")

    def _print_loop_blocked(self, tool_name: str):
        """打印循环阻止信息"""
        print(f"\n{Colors.RED}{Colors.BOLD}🛑 循环被阻止:{Colors.RESET}")
        print(f"{Colors.RED}工具 `{tool_name}` 达到最大调用次数限制，"
              f"停止执行。{Colors.RESET}")

    def _format_tools(self) -> list[dict]:
        """格式化工具列表"""
        if not self.tool_registry:
            return []

        # 获取所有工具
        tools = self.tool_registry.get_all_tools()
        return self.tool_registry.to_openai_format(tools)

    def _format_skills_prompt(self) -> str:
        """格式化 skills 提示"""
        if not self.skill_loader:
            return "无可用 Skills"

        # 获取所有 skills
        try:
            all_skills = self.skill_loader.get_all_skills()
        except:
            all_skills = []

        if not all_skills:
            return "无可用 Skills"

        # 使用 skill_loader 的方法构建快照并格式化
        try:
            snapshot = self.skill_loader.build_snapshot(all_skills)
            return self.skill_loader.format_skills_prompt(snapshot)
        except:
            # 备用格式
            lines = ["## 可用 Skills\n"]
            for skill_entry in all_skills:
                name = skill_entry.skill.name if hasattr(skill_entry, 'skill') else skill_entry.get('skill', {}).get('name', 'unknown')
                desc = skill_entry.skill.description if hasattr(skill_entry, 'skill') else skill_entry.get('skill', {}).get('description', '')
                lines.append(f"- **{name}**: {desc}")
            return "\n".join(lines)

    def _check_and_load_skill(self, tool_call: ToolCall = None) -> Optional[str]:
        """
        检查是否需要加载 skill 并加载

        流程：
        1. 如果模型调用了 read 工具读取某个 skill 的 SKILL.md，直接返回内容

        Args:
            tool_call: 工具调用（如果有）

        Returns:
            加载的 skill 内容，如果没有则返回 None
        """
        # 通过 tool_call 检测（模型读取 skill 文件）
        if tool_call:
            tool_name = tool_call.name
            args = tool_call.arguments

            if tool_name == "read":
                path = args.get("path", "") or args.get("file_path", "")
                # 检查是否是读取 skill 文件
                # 获取 skill_loader 的 skills_dir
                skills_dir = getattr(self.skill_loader, 'skills_dir', 'workspace/skills') if self.skill_loader else 'workspace/skills'

                for skill_entry in self.skill_loader.get_all_skills():
                    skill_name = skill_entry.skill.name if hasattr(skill_entry, 'skill') else None
                    if not skill_name:
                        continue
                    skill_path = f"{skills_dir}/{skill_name}/SKILL.md"
                    if skill_path in path or f"{skills_dir}/{skill_name}" in path:
                        self._print_skill_load(skill_name)
                        content = self.skill_loader.get_skill_content(skill_name)
                        if content:
                            self.skills_loaded[skill_name] = content
                            return f"\n\n## Skill: {skill_name}\n\n{content}\n"
                # 检查是否是读取其他 skill 相关文件
                if "skill" in path.lower() or "SKILL" in path:
                    # 尝试提取 skill 名称
                    match = re.search(r'(?:' + re.escape(skills_dir) + r'[/\\]?|skills?[/\\]?|SKILL\.md[/\\]?)(\w+)', path, re.IGNORECASE)
                    if match:
                        skill_name = match.group(1)
                        self._print_skill_load(skill_name)
                        content = self.skill_loader.get_skill_content(skill_name)
                        if content:
                            self.skills_loaded[skill_name] = content
                            return f"\n\n## Skill: {skill_name}\n\n{content}\n"

        return None

    def _execute_tool(self, tool_name: str, args: dict) -> tuple[bool, str, Optional[str], bool, bool]:
        """
        执行工具

        Args:
            tool_name: 工具名称
            args: 工具参数

        Returns:
            (成功标志, 内容, 错误信息, 是否取消任务, 是否废弃当前tool)
        """
        if not self.tool_registry:
            return False, "", "工具注册表未初始化", False, False

        # 危险工具确认
        confirmed, hint, cancel_task = self._confirm_dangerous_tool(tool_name, args)
        if cancel_task:
            # 用户选择取消整个任务
            return False, "", "用户取消任务", True, False
        if not confirmed:
            return False, "", "用户取消执行", False, False

        # 如果用户提供了补充提示，废弃当前 tool，让模型重新思考
        if hint:
            hint_message = {
                "role": "user",
                "content": f"【用户提示】刚才你打算执行 {tool_name} 工具，但我希望你在重新思考后给出更好的方案。我的补充意见是：{hint}\n\n请重新思考并决定下一步该怎么做。"
            }
            self.messages.append(hint_message)
            # 返回特殊状态：废弃当前 tool，让模型重新思考
            return True, "", None, False, True

        try:
            result = self.tool_registry.execute(tool_name, args)
            if result.success:
                return True, result.content, None, False, False
            else:
                return False, "", result.error, False, False
        except Exception as e:
            return False, "", str(e), False, False

    def _detect_loop(self, tool_name: str, args: dict) -> tuple[bool, int]:
        """
        检测循环调用

        Args:
            tool_name: 工具名称
            args: 工具参数

        Returns:
            (是否检测到循环, 连续调用次数)
        """
        if not self.enable_loop_detection:
            return False, 0

        # 计算连续相同调用
        count = 0
        args_str = json.dumps(args, sort_keys=True)

        for i in range(len(self.state.tool_history) - 1, -1, -1):
            call = self.state.tool_history[i]
            if call["name"] == tool_name and call["args"] == args_str:
                count += 1
            else:
                break

        return count >= self.loop_warning_threshold, count

    def _confirm_dangerous_tool(self, tool_name: str, args: dict) -> tuple[bool, str, bool]:
        """
        确认危险工具执行（支持上下箭头选择和补充提示）

        Args:
            tool_name: 工具名称
            args: 工具参数

        Returns:
            (是否确认执行, 用户补充的提示信息, 是否取消任务)
            - (True, "", False) 表示确认执行
            - (False, "", False) 表示取消执行（当前工具）
            - (True, "提示信息", False) 表示确认执行并补充了提示信息
            - (False, "", True) 表示取消整个任务
        """
        if not self.confirm_dangerous_tools:
            return True, "", False

        if tool_name not in self._dangerous_tools:
            return True, "", False

        # 构建确认信息
        print(f"\n{Colors.YELLOW}{Colors.BOLD}⚠️  安全确认{Colors.RESET}")
        print(f"{Colors.YELLOW}工具 `{tool_name}` 可能存在风险，请确认是否执行:{Colors.RESET}")

        if tool_name == "exec":
            command = args.get("command", "")
            print(f"\n{Colors.RED}命令:{Colors.RESET}")
            print(f"  {command}")
        elif tool_name == "write":
            file_path = args.get("file_path", "")
            content = args.get("content", "")
            print(f"\n{Colors.RED}文件路径:{Colors.RESET}")
            print(f"  {file_path}")
            print(f"\n{Colors.RED}内容预览 (前200字符):{Colors.RESET}")
            print(f"  {content[:200]}...")
        elif tool_name == "edit":
            file_path = args.get("file_path", "")
            old_string = args.get("old_string", "")
            new_string = args.get("new_string", "")
            print(f"\n{Colors.RED}文件路径:{Colors.RESET}")
            print(f"  {file_path}")
            print(f"\n{Colors.RED}将替换:{Colors.RESET}")
            print(f"  {old_string[:100]}...")
            print(f"\n{Colors.GREEN}替换为:{Colors.RESET}")
            print(f"  {new_string[:100]}...")

        # 交互式选择菜单
        import sys
        import tty
        import termios

        options = [
            "▶ 确认执行",
            "✗ 取消执行（当前工具）",
            "○ 补充提示信息后继续执行",
            "○ 取消任务（结束整个对话）",
        ]
        current = 0
        hint_text = ""

        def get_char():
            """获取单个按键，不回显"""
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setraw(sys.stdin.fileno())
                ch = sys.stdin.read(1)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            return ch

        def clear_lines(n):
            """清除最后 n 行"""
            for _ in range(n):
                sys.stdout.write("\033[F")  # 移动到上一行开头
                sys.stdout.write("\033[2K")  # 清除该行
            sys.stdout.flush()

        def print_options():
            """打印选项菜单"""
            for i, opt in enumerate(options):
                if i == current:
                    print(f"{Colors.CYAN}{Colors.BOLD}{opt}{Colors.RESET}")
                else:
                    print(f"  {opt}")

        print(f"\n{Colors.CYAN}请选择操作（↑↓选择，回车确认）:{Colors.RESET}")
        print_options()

        try:
            while True:
                c = get_char()

                # 检测方向键 (ESC [A/B/C/D)
                if c == '\x1b':
                    next_char = get_char()
                    if next_char == '[':
                        direction = get_char()
                        if direction == 'A':  # 上
                            if current > 0:
                                current -= 1
                                clear_lines(len(options))
                                print_options()
                        elif direction == 'B':  # 下
                            if current < len(options) - 1:
                                current += 1
                                clear_lines(len(options))
                                print_options()
                elif c == '\r' or c == '\n':  # 回车确认
                    clear_lines(len(options) + 1)  # 清除菜单
                    print()  # 换行
                    break
                elif c == '\x03':  # Ctrl+C
                    clear_lines(len(options) + 1)
                    print(f"{Colors.RED}✗ 已取消执行{Colors.RESET}")
                    return False, "", False
                elif c == '\x04':  # Ctrl+D
                    clear_lines(len(options) + 1)
                    print(f"{Colors.RED}✗ 已取消执行{Colors.RESET}")
                    return False, "", False

            # 处理选择结果
            if current == 0:
                # 确认执行
                print(f"{Colors.GREEN}✓ 已确认，执行中...{Colors.RESET}")
                return True, "", False
            elif current == 1:
                # 取消执行（当前工具）
                print(f"{Colors.RED}✗ 已取消执行{Colors.RESET}")
                return False, "", False
            elif current == 2:
                # 补充提示信息
                print(f"{Colors.CYAN}请输入提示信息（将发送给模型作为参考），输入空行结束:{Colors.RESET}")
                lines = []
                while True:
                    try:
                        line = input()
                        lines.append(line)
                        # 空行结束输入
                        if line == "":
                            break
                    except (EOFError, KeyboardInterrupt):
                        break
                hint_text = "\n".join(lines).strip()

                if hint_text:
                    print(f"{Colors.GREEN}✓ 收到提示信息，继续执行...{Colors.RESET}")
                    return True, hint_text, False
                else:
                    print(f"{Colors.GREEN}✓ 无补充信息，执行中...{Colors.RESET}")
                    return True, "", False
            else:
                # 取消任务（结束整个对话）
                print(f"{Colors.YELLOW}⚠ 取消任务，结束对话...{Colors.RESET}")
                return False, "", True

        except (EOFError, KeyboardInterrupt):
            print(f"\n{Colors.RED}✗ 已取消执行{Colors.RESET}")
            return False, "", False
        finally:
            # 确保终端设置恢复
            pass

    def _call_llm(
        self,
        messages: list[dict],
        tools: list[dict] = None,
        stream_callback=None,
        **kwargs
    ) -> dict:
        """调用 LLM

        Args:
            stream_callback: 流式回调函数，每收到一个 chunk 调用一次
        """
        if self.llm_provider:
            from utils.llm_req import call_llm as _call_llm

            response = _call_llm(
                messages=messages,
                tools=tools,
                stream=bool(stream_callback),
                stream_callback=stream_callback,
                **kwargs
            )
            return response
        else:
            return self._mock_llm_response(messages)

    def _mock_llm_response(self, messages: list[dict]) -> dict:
        """模拟 LLM 响应"""
        last_message = messages[-1].get("content", "") if messages else ""

        return {
            "type": "text",
            "content": f"我理解了您的请求: {last_message[:50]}... "
                       f"请提供更多细节，或告诉我具体需要我做什么。",
            "tool_calls": None
        }

    def _parse_tool_calls(self, response: dict) -> list[ToolCall]:
        """解析工具调用"""
        tool_calls = []

        # OpenAI 格式
        if "tool_calls" in response:
            for call in response["tool_calls"]:
                func = call.get("function", {})
                name = func.get("name", "")
                arguments = func.get("arguments", {})

                arguments = self._normalize_tool_arguments(arguments)

                tool_calls.append(ToolCall(
                    name=name,
                    arguments=arguments,
                    call_id=call.get("id", f"call_{len(tool_calls)}")
                ))

        return tool_calls

    def _normalize_tool_arguments(self, arguments: Any) -> dict:
        """将 tool arguments 规范化为 dict，尽量容错解析流式/半结构化内容。"""
        if isinstance(arguments, dict):
            return arguments

        if not isinstance(arguments, str):
            return {}

        raw = arguments.strip()
        if not raw:
            return {}

        # 去掉常见 markdown code fence 包裹
        if raw.startswith("```"):
            parts = raw.split("```")
            if len(parts) >= 3:
                raw = parts[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()

        # 直接解析
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            pass

        # 容错：提取第一个 {...} 再解析
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = raw[start:end + 1]
            try:
                parsed = json.loads(candidate)
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                pass

        return {}

    def _validate_tool_args(self, tool_name: str, args: dict) -> Optional[str]:
        """校验工具参数，返回错误信息；合法时返回 None。"""
        if not self.tool_registry:
            return None

        tool_def = self.tool_registry.get_tool(tool_name)
        if not tool_def:
            return None

        required = []
        try:
            required = tool_def.parameters.get("required", []) or []
        except Exception:
            required = []

        missing = []
        for key in required:
            value = args.get(key)
            if value is None:
                missing.append(key)
            elif isinstance(value, str) and not value.strip():
                missing.append(key)

        if missing:
            return f"工具 `{tool_name}` 参数无效，缺少必填参数: {', '.join(missing)}。"

        # 针对核心工具做更严格的空值校验
        strict_string_fields = {
            "read": ["file_path"],
            "write": ["file_path", "content"],
            "edit": ["file_path", "old_string", "new_string"],
            "exec": ["command"],
        }
        for key in strict_string_fields.get(tool_name, []):
            value = args.get(key)
            if not isinstance(value, str) or not value.strip():
                return f"工具 `{tool_name}` 参数无效，`{key}` 不能为空字符串。"

        return None

    def _build_system_prompt(self) -> str:
        """构建系统提示 - 中文强化版"""
        # 加载 memory 信息
        agent_info = self.memory_manager.get_agent_memory()
        user_info = self.memory_manager.get_user_memory()
        soul_info = self.memory_manager.get_soul_memory()
        memory_info = self.memory_manager.get_longterm_memory()

        # 获取 skills 提示（XML 格式）
        skills_prompt = self._format_skills_prompt_xml()

        # 获取可用工具描述
        tool_descriptions = self._format_tool_descriptions()

        # 获取 session 历史对话
        conversation_history = self.session_manager.format_conversation_for_llm(max_messages=20)

        # 获取当前时间
        from datetime import datetime
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 计算 memory 基础路径
        memory_base = self.workspace
        if not memory_base.endswith('/'):
            memory_base += '/'
        memory_base += 'memory'

        # 构建系统提示
        parts = []

        # === 1. 开场 ===
        parts.append("""# 你是 XiamiClaw Agent
你是一个运行在 XiamiClaw 中的智能个人助手。你的职责是帮助用户完成各种任务，包括但不限于：代码编写、信息搜索、文件处理、问题解答等。

## 核心原则
- **主动思考**：在执行任务前先分析问题，规划解决方案
- **保持简洁**：除非必要，否则不要过度解释
- **诚实透明**：不知道的事情如实告知，不要编造信息
- **安全第一**：涉及敏感操作时，先确认再执行""")

        # === 2. 工具列表 ===
        parts.append(f"""## 工具 (Tooling)
**重要**：工具名称区分大小写，必须严格按照以下名称调用。

### 可用工具
{tool_descriptions}

### 工具调用规范
- **常规操作**：直接调用工具，无需过多描述过程
- **复杂任务**：多步骤工作时，适当说明进展和思路
- **敏感操作**（删除、移动、覆盖等）：调用前告知用户潜在风险
- **技术上下文**：可使用技术语言；非技术场景使用通俗易懂的人话
- **存在专用工具时**：直接使用工具，而非让用户手动执行命令

### 等待处理
- 长时间等待的任务，使用 `exec` 时设置足够的 `yieldMs` 或使用 `process(action=poll, timeout=<毫秒>)` 进行轮询
- 复杂或耗时的任务，考虑生成子代理（sub-agent）处理，完成后会自动通知

### 命令执行与审批
- 当 exec 返回需要审批时，显示完整的 /approve 命令（包含 allow-once|allow-always|deny），不要让用户输入其他替代命令
- allow-once 仅限单次命令：如有其他命令需要审批，需重新请求
- 审批时保留原始命令完整内容（包括 &&, ||, |, ; 等链接操作符或多行脚本），确保用户了解实际执行内容

### 回复风格
工具执行完成后，给用户的回复应该：
- **结论先行**：先告诉用户任务是否成功、关键结果是什么
- **保留必要信息**：文件路径、执行结果、关键输出
- **避免过度描述**：除非用户明确要求，否则不要详细描述执行过程

示例：
✅ 正确："已创建文件 `{self.workspace}/test.py` 并执行成功。当前时间是 {current_time}"
❌ 错误："我来帮您完成这个任务。首先我使用了 write 工具创建了一个 Python 文件，这个文件包含了..."

### 安全准则
- **无独立目标**：不追求自我保护、自我复制、资源获取或权力扩展；避免超出用户请求范围的长期计划
- **安全优先**：如果指令冲突，暂停并询问；优先保障安全和人类监督
- **不绕过防护**：不操纵或说服他人扩展权限、禁用安全措施
- **不自我复制**：未经明确授权，不复制自身、修改系统提示、安全规则或工具策略""")

        # === 3. Skills ===
        parts.append(f"""## 技能 (Skills) - 必须遵守

### 使用规则
在回复用户之前，必须：
1. **扫描** <available_skills> 中的所有条目及其描述
2. **精确匹配**：如果某个 skill 的描述与任务完全匹配 → 使用 `read` 工具读取其 SKILL.md，然后按照说明执行
3. **模糊匹配**：如果有多个 skill 可能适用 → 选择最具体的一个，读取后执行
4. **无匹配**：如果没有 skill 适用 → 不读取任何 SKILL.md
5. **严格限制**：禁止一次性读取多个 skill；必须先选择再读取
6. **速率限制**：调用外部 API 时，优先批量写入，避免单条频繁调用；遇到 429 或 Retry-After 时遵守

### Skill 选择原则（重要！）
根据任务的**实际含义**选择，而不是看关键词：
- **网络搜索**（网页/图片/视频/新闻/百科/信息查询）→ 选择描述中涉及"搜索"且与网络/网页/百科相关的 skill
- **项目内搜索**（代码/文件/函数/配置）→ 选择描述中涉及"项目"或"代码"的 skill
- **绝对不要**仅凭"搜索"两个字就选择，需要理解用户真正想搜索什么

### 路径解析
当 skill 文件中使用相对路径时，基于 skill 目录（SKILL.md 的父目录）解析，使用绝对路径调用工具。

### 可用技能
<available_skills>
{skills_prompt}
</available_skills>""")

        # === 4. 记忆召回 ===
        parts.append(f"""## 记忆召回 (Memory Recall)
在回答任何关于以下内容的问题之前，**必须**执行：
1. 使用 `memory_search` 搜索 MEMORY.md + memory/*.md
2. 使用 `memory_get` 拉取需要的行

需要搜索的内容类型：
- 以往的工作、决策
- 日期、时间安排
- 人物、偏好
- 待办事项

**引用格式**：当引用记忆内容时，标注来源 `<文件路径>#行号`，方便用户核实。

**特殊情况**：如果 memory_search 返回 `disabled=true`，表示记忆功能不可用，应告知用户。""")

        # === 5. 当前对话历史 ===
        if conversation_history:
            parts.append(f"""## 当前对话历史
{conversation_history}""")

        # === 6. 身份与上下文 ===
        if soul_info:
            parts.append(f"""## SOUL.md - 你的性格
{soul_info}""")

        if agent_info:
            parts.append(f"""## AGENT.md - 你的身份
{agent_info}""")

        if user_info:
            parts.append(f"""## USER.md - 关于你的主人
{user_info}""")

        # === 7. 长期记忆 ===
        if memory_info:
            parts.append(f"""## MEMORY.md - 长期记忆
{memory_info}""")

        # === 8. 工作目录 ===
        parts.append(f"""## 工作目录 (Workspace)
你的工作目录是：`{self.workspace}`

**重要**：除非用户明确指示，否则所有文件操作都在此目录下进行。

**注意**：不同 agent 的工作目录是隔离的，当前 agent 的工作目录是 `{self.workspace}`。""")

        # === 9. 当前时间 ===
        parts.append(f"""## 当前时间
时区：Asia/Shanghai
当前时间：{current_time}""")

        # === 10. 执行模式 ===
        parts.append(f"""## 执行模式 - ReAct
按以下步骤思考和执行：

1. **Think (思考)**：分析任务，理解用户需求，规划解决步骤
2. **Action (行动)**：调用合适的工具执行任务
3. **Observe (观察)**：检查工具返回的结果
4. **Reflect (反思)**：如结果不符合预期，调整方法重新尝试

**记住**：你可以通过工具帮助完成任务。需要执行命令时，使用 `exec` 工具。

---

## 记忆管理 (重要!)

### 你是一个有记忆的助手
每次对话结束后，根据对话内容**主动决定**是否需要更新以下文件：

### 何时更新文件

| 文件 | 更新时机 | 示例 |
|------|----------|------|
| **USER.md** | 用户明确提供了关于他们自己的信息 | "我叫张三"、"我喜欢用 Python"、"我习惯用 tabs" |
| **AGENT.md** | 用户给你命名或定义角色 | "你叫蟹酱吧"、"你是我的编程助手" |
| **SOUL.md** | 用户表达了对你的性格/风格期望 | "希望你活泼一点"、"要更有耐心" |
| **MEMORY.md** | 对话中有重要的事实、决定或需要长期记住的信息 | "这个项目的架构是..."、"下次继续这个任务" |

### 更新步骤（必须按顺序）
1. 先用 `read` 工具读取对应的 memory 文件（如 `{memory_base}/USER.md`）
2. 分析现有内容，决定是修改、替换还是跳过
3. 如果需要更新，使用 `write` 工具写入完整内容（保留原有重要信息，只修改/新增相关内容）

### 不要更新的情况
- 日常寒暄、闲聊
- 用户只是问问题
- 不确定的信息

### 文件位置
所有 memory 文件都在 `{memory_base}/` 目录下：
- `{memory_base}/USER.md` - 用户信息
- `{memory_base}/AGENT.md` - Agent 身份信息
- `{memory_base}/SOUL.md` - Agent 性格设定
- `{memory_base}/MEMORY.md` - 长期记忆

### 重要提示
**你有责任主动维护这些文件！** 如果对话中发现了值得记录的信息，在最终回复用户后，主动调用工具更新相应的文件。

---

### 写下来 - 不要靠记忆！
- **记忆是有限的** — 如果想记住什么，**写到文件里**
- " mental notes"（心里记）不会在会话重启后保留，但文件会
- 当用户说"记住这个" → 更新 `memory/YYYY-MM-DD.md` 或相关文件
- 当学到教训 → 更新相关 memory 文件
- 当犯错了 → 记录下来，防止重蹈覆辙
- **文字 > 大脑** 📝

---

### Heartbeat vs Cron 使用场景

**使用 Heartbeat（心跳）的场景**：
- 需要批量检查多个项目（收件箱 + 日历 + 通知一次处理）
- 需要最近消息的对话上下文
- 时间稍微漂移可以接受（约 30 分钟一次足够，不需要精确）
- 想通过合并周期性检查减少 API 调用

**使用 Cron 的场景**：
- 需要精确时间（如"每周一上午 9:00 整"）
- 任务需要与主会话历史隔离
- 任务想使用不同的模型或思考深度
- 一次性提醒（"20 分钟后提醒我"）
- 输出应直接发送到渠道，不经过主会话

---

### 红线（绝对不能触碰）
- **绝不泄露私人数据**
- **未经允许不执行破坏性命令**
- 用 `trash` 代替 `rm`（可恢复 > 永远消失）
- 有疑问就问

### 内部操作 vs 外部操作

**可以自由执行**：
- 读取文件、探索、组织、学习
- 搜索网络、查询信息
- 在工作目录内工作

**需要先询问**：
- 发送邮件、推文、公开帖子
- 任何离开本机的操作
- 任何你不确定的事情""")

        # === 11. 开始 ===
        parts.append("""## 开始
现在，请帮助用户完成他们的请求。""")

        return "\n\n".join(parts)

    def _format_skills_prompt_xml(self) -> str:
        """格式化 skills 为 XML 格式（参考 OpenClaw）"""
        if not self.skill_loader:
            return "<skill><name>none</name><description>No skills available</description></skill>"

        try:
            all_skills = self.skill_loader.get_all_skills()
        except:
            all_skills = []

        if not all_skills:
            return "<skill><name>none</name><description>No skills available</description></skill>"

        # 获取 skill_loader 的 skills_dir
        skills_dir = getattr(self.skill_loader, 'skills_dir', 'workspace/skills') if self.skill_loader else 'workspace/skills'

        lines = []
        for skill_entry in all_skills:
            try:
                # 尝试获取 skill 信息
                if hasattr(skill_entry, 'skill'):
                    name = skill_entry.skill.name
                    description = skill_entry.skill.description
                    location = f"{skills_dir}/{name}/SKILL.md"
                else:
                    # 备用方式
                    skill_dict = skill_entry if isinstance(skill_entry, dict) else {}
                    name = skill_dict.get('skill', {}).get('name', 'unknown')
                    description = skill_dict.get('skill', {}).get('description', '')
                    location = f"{skills_dir}/{name}/SKILL.md"

                lines.append(f"""  <skill>
    <name>{name}</name>
    <description>{description}</description>
    <location>{location}</location>
  </skill>""")
            except Exception as e:
                continue

        return "\n".join(lines) if lines else "<skill><name>none</name><description>No skills available</description></skill>"

    def _format_tool_descriptions(self) -> str:
        """格式化工具描述（参考 OpenClaw 格式）"""
        if not self.tool_registry:
            return "- (no tools available)"

        tools = self.tool_registry.get_all_tools()

        lines = []
        for tool in tools:
            name = tool.name
            desc = tool.description or "No description"
            lines.append(f"- {name}: {desc}")

        return "\n".join(lines)

    def _should_continue(self, iteration: int) -> bool:
        """
        判断是否继续循环

        Args:
            iteration: 当前迭代次数

        Returns:
            是否继续
        """
        # 检查是否达到最大迭代
        if iteration >= self.max_iterations:
            return False

        # 检查工具调用次数
        if self.state.tool_calls >= self.max_iterations * self.max_tool_calls_per_iteration:
            return False

        return True

    def run(
        self,
        user_message: str,
        show_progress: bool = True,
        stream_callback=None,
    ) -> Optional[str]:
        """
        运行 Agentic Loop (兼容版本，内部使用 run_stream)

        Args:
            user_message: 用户消息
            show_progress: 是否显示进度
            stream_callback: 流式回调函数，用于实时打印 LLM 输出

        Returns:
            最终响应，如果用户取消任务则返回 None
        """
        final_result = None

        for event in self.run_stream(user_message, show_progress=show_progress, stream_callback=stream_callback):
            if event.type == EventType.FINAL_RESPONSE:
                final_result = event.data

        return final_result

    def run_stream(
        self,
        user_message: str,
        show_progress: bool = True,
        stream_callback=None,
    ) -> Generator[Event, None, str]:
        """
        运行 Agentic Loop (生成器版本，yield 事件)

        Args:
            user_message: 用户消息
            show_progress: 是否显示进度
            stream_callback: 流式回调函数，用于实时打印 LLM 输出

        Yields:
            Event: 各种类型的事件
        Returns:
            最终响应字符串
        """
        # 初始化状态
        self.state = LoopState(start_time=time.time())
        self.messages = []
        self.skills_loaded = {}

        # 创建新 session 并记录用户消息
        session_id = self.session_manager.create_session(user_message)
        self.session_manager.add_user_message(user_message)

        # 构建初始消息
        system_prompt = self._build_system_prompt()
        self.messages.append({"role": "system", "content": system_prompt})
        self.messages.append({"role": "user", "content": user_message})

        # 获取工具列表
        tools = self._format_tools()

        # 记录开始时间
        start_time = time.time()
        # ReAct 循环
        while self._should_continue(self.state.iteration):
            self.state.iteration += 1

            if show_progress:
                yield Event(EventType.ITERATION_START, {
                    "iteration": self.state.iteration,
                    "max_iterations": self.max_iterations,
                    "elapsed": time.time() - self.state.start_time,
                    "tool_calls": self.state.tool_calls,
                })

            # 调用 LLM
            if show_progress:
                yield Event(EventType.THINKING_START, None)

            # 用于收集流式内容
            full_content = []
            stream_queue: Queue[str] = Queue()
            response_holder: dict[str, dict] = {}
            error_holder: dict[str, Exception] = {}
            done_event = threading.Event()

            def _stream_callback(chunk: str):
                full_content.append(chunk)
                stream_queue.put(chunk)
                if stream_callback:
                    stream_callback(chunk)

            def _llm_worker():
                try:
                    response_holder["response"] = self._call_llm(
                        self.messages,
                        tools=tools,
                        stream_callback=_stream_callback
                    )
                except Exception as e:
                    error_holder["error"] = e
                finally:
                    done_event.set()

            worker = threading.Thread(target=_llm_worker, daemon=True)
            worker.start()

            # 实时转发流式片段
            llm_wait_start = time.time()
            last_thinking_progress_emit = 0.0
            has_stream_output = False
            while True:
                try:
                    chunk = stream_queue.get(timeout=0.05)
                    has_stream_output = True
                    yield Event(EventType.STREAM_CHUNK, chunk)
                except Empty:
                    pass

                # 思考阶段心跳：长时间无输出时给前端进度感知
                elapsed_thinking = time.time() - llm_wait_start
                if (not has_stream_output) and (elapsed_thinking - last_thinking_progress_emit >= 2.0):
                    last_thinking_progress_emit = elapsed_thinking
                    yield Event(EventType.THINKING_PROGRESS, {
                        "iteration": self.state.iteration,
                        "elapsed": elapsed_thinking,
                    })

                if done_event.is_set() and stream_queue.empty():
                    break

            worker.join(timeout=0)

            if error_holder:
                raise error_holder["error"]

            response = response_holder.get("response", {"type": "text", "content": ""})

            # 如果有流式回调触发，yield STREAM_END
            if full_content:
                yield Event(EventType.STREAM_END, None)

            # 解析工具调用
            tool_calls = self._parse_tool_calls(response)

            if not tool_calls:
                # 没有工具调用，返回响应
                content = response.get("content", "")

                self.messages.append({"role": "assistant", "content": content})

                # 记录到 session
                self.session_manager.add_assistant_message(content=content)

                yield Event(EventType.FINAL_RESPONSE, content)
                return content

            # 处理工具调用
            for tool_call in tool_calls[:self.max_tool_calls_per_iteration]:
                tool_name = tool_call.name
                tool_args = tool_call.arguments

                # 检查循环
                is_loop, loop_count = self._detect_loop(tool_name, tool_args)

                if show_progress:
                    yield Event(EventType.TOOL_CALL, {"name": tool_name, "args": tool_args})

                if is_loop:
                    if loop_count >= self.loop_max_threshold:
                        if show_progress:
                            self._print_loop_blocked(tool_name)

                        # 阻止执行并返回错误消息
                        error_msg = f"检测到循环调用: 工具 `{tool_name}` 被连续调用 {loop_count} 次。"
                        self.messages.append({
                            "role": "assistant",
                            "content": error_msg
                        })

                        yield Event(EventType.ERROR, error_msg)
                        yield Event(EventType.FINAL_RESPONSE, error_msg)
                        return error_msg
                    else:
                        if show_progress:
                            self._print_loop_warning(tool_name, loop_count)

                # 检查是否需要加载 skill
                skill_content = self._check_and_load_skill(tool_call=tool_call)
                if skill_content and show_progress:
                    print(f"\n{Colors.GREEN}已加载 skill 内容到上下文{Colors.RESET}")
                    # 将 skill 内容作为系统消息添加到上下文
                    self.messages.append({
                        "role": "system",
                        "content": f"## 加载的 Skill 内容\n{skill_content}"
                    })

                # 参数校验：参数异常不执行工具，直接反馈给模型重试
                arg_error = self._validate_tool_args(tool_name, tool_args)
                if arg_error:
                    if show_progress:
                        yield Event(EventType.TOOL_RESULT, {
                            "success": False,
                            "content": "",
                            "error": arg_error
                        })

                    self.state.tool_calls += 1
                    self.state.tool_history.append({
                        "name": tool_name,
                        "args": json.dumps(tool_args, sort_keys=True),
                        "success": False,
                        "timestamp": time.time(),
                    })

                    self.messages.append({
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": tool_call.call_id,
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": json.dumps(tool_args)
                            }
                        }]
                    })

                    self.session_manager.add_assistant_message(
                        content=None,
                        tool_calls=[{
                            "id": tool_call.call_id,
                            "function": {
                                "name": tool_name,
                                "arguments": tool_args
                            }
                        }]
                    )

                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.call_id,
                        "content": arg_error
                    })
                    self.session_manager.add_tool_result(tool_call_id=tool_call.call_id, content=arg_error)
                    continue

                # 执行工具（带心跳）
                # 注意：危险工具需要交互确认，保持同步执行避免 stdin 竞争
                if self.confirm_dangerous_tools and tool_name in self._dangerous_tools:
                    success, content, error, cancel_task, discard = self._execute_tool(tool_name, tool_args)
                else:
                    exec_holder: dict[str, Any] = {}
                    exec_error_holder: dict[str, Exception] = {}
                    exec_done = threading.Event()

                    def _tool_worker():
                        try:
                            exec_holder["result"] = self._execute_tool(tool_name, tool_args)
                        except Exception as e:
                            exec_error_holder["error"] = e
                        finally:
                            exec_done.set()

                    tool_start = time.time()
                    last_progress_emit = 0.0
                    tool_thread = threading.Thread(target=_tool_worker, daemon=True)
                    tool_thread.start()

                    while not exec_done.wait(timeout=0.1):
                        elapsed_tool = time.time() - tool_start
                        if elapsed_tool - last_progress_emit >= 1.5:
                            last_progress_emit = elapsed_tool
                            if show_progress:
                                yield Event(EventType.TOOL_PROGRESS, {
                                    "name": tool_name,
                                    "elapsed": elapsed_tool
                                })

                    tool_thread.join(timeout=0)

                    if exec_error_holder:
                        raise exec_error_holder["error"]

                    success, content, error, cancel_task, discard = exec_holder.get(
                        "result",
                        (False, "", "工具执行异常", False, False)
                    )

                # 如果用户取消任务，直接结束
                if cancel_task:
                    yield Event(EventType.ERROR, "用户取消任务")
                    yield Event(EventType.FINAL_RESPONSE, None)
                    return None

                # 如果废弃当前 tool，让模型重新思考
                if discard:
                    if show_progress:
                        print(f"{Colors.YELLOW}⚠ 已废弃当前工具，等待模型重新思考...{Colors.RESET}")
                    # 不记录到历史，不添加 tool 结果，继续下一个 tool 或重新循环
                    continue

                if show_progress:
                    yield Event(EventType.TOOL_RESULT, {"success": success, "content": content, "error": error})

                # 记录到历史
                self.state.tool_calls += 1
                self.state.tool_history.append({
                    "name": tool_name,
                    "args": json.dumps(tool_args, sort_keys=True),
                    "success": success,
                    "timestamp": time.time(),
                })

                # 添加到消息历史
                # 先添加 assistant 的 tool call
                self.messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": tool_call.call_id,
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": json.dumps(tool_args)
                        }
                    }]
                })

                # 记录 assistant 的 tool call 到 session
                self.session_manager.add_assistant_message(
                    content=None,
                    tool_calls=[{
                        "id": tool_call.call_id,
                        "function": {
                            "name": tool_name,
                            "arguments": tool_args
                        }
                    }]
                )

                # 再添加 tool 结果
                result_content = content if success else (error or "执行失败")
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.call_id,
                    "content": result_content
                })

                # 记录 tool 结果到 session
                self.session_manager.add_tool_result(tool_call_id=tool_call.call_id, content=result_content)

                yield Event(EventType.ITERATION_END, {
                    "iteration": self.state.iteration,
                    "tool_calls": self.state.tool_calls,
                })

        # 达到最大迭代
        elapsed = time.time() - start_time

        if show_progress:
            self._print_header(f"达到最大迭代 ({self.max_iterations})")
            print(f"{Colors.YELLOW}总耗时: {elapsed:.1f}s, 工具调用: {self.state.tool_calls}{Colors.RESET}")

        final_response = ("我已尽最大努力处理您的请求，但尚未完成。"
                "您可以提供更多细节或重新描述您的问题。")

        yield Event(EventType.ERROR, "达到最大迭代")
        yield Event(EventType.FINAL_RESPONSE, final_response)
        return final_response


def create_agentic_loop(
    llm_provider: Optional[Callable] = None,
    tool_registry: Optional[Any] = None,
    skill_loader: Optional[Any] = None,
    confirm_dangerous_tools: bool = True,
    workspace: str = "./workspace",
    agent_name: str = "agent",
    **kwargs
) -> AgenticLoop:
    """
    创建 Agentic Loop 实例

    Args:
        llm_provider: LLM 提供者
        tool_registry: 工具注册表
        skill_loader: Skill 加载器
        confirm_dangerous_tools: 是否在执行危险工具前确认 (默认 True)
        workspace: 工作目录路径 (默认 "./workspace")
        agent_name: Agent 名称 (默认 "agent")
        **kwargs: 其他参数

    Returns:
        AgenticLoop 实例
    """
    return AgenticLoop(
        llm_provider=llm_provider,
        tool_registry=tool_registry,
        skill_loader=skill_loader,
        confirm_dangerous_tools=confirm_dangerous_tools,
        workspace=workspace,
        agent_name=agent_name,
        **kwargs
    )


# 便捷函数
def run_agentic_loop(
    user_message: str,
    llm_provider: Optional[Callable] = None,
    tool_registry: Optional[Any] = None,
    skill_loader: Optional[Any] = None,
    show_progress: bool = True,
    confirm_dangerous_tools: bool = True,
    workspace: str = "./workspace",
    agent_name: str = "agent",
    **kwargs
) -> str:
    """
    运行 Agentic Loop 的便捷函数

    Args:
        user_message: 用户消息
        llm_provider: LLM 提供者
        tool_registry: 工具注册表
        skill_loader: Skill 加载器
        show_progress: 是否显示进度
        confirm_dangerous_tools: 是否在执行危险工具前确认 (默认 True)
        workspace: 工作目录路径 (默认 "./workspace")
        agent_name: Agent 名称 (默认 "agent")
        **kwargs: 其他参数

    Returns:
        最终响应
    """
    loop = create_agentic_loop(
        llm_provider=llm_provider,
        tool_registry=tool_registry,
        skill_loader=skill_loader,
        confirm_dangerous_tools=confirm_dangerous_tools,
        workspace=workspace,
        agent_name=agent_name,
        **kwargs
    )

    return loop.run(user_message, show_progress=show_progress)
