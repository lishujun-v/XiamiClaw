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
import logging
import threading
from queue import Empty, Queue
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
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
from utils.config import get_agent_config
from utils.logging_utils import format_trace_message, summarize_for_log, summarize_tool_result, truncate_for_log


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
        logger=None,
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
        self.logger = logger or logging.getLogger("xiamiclaw.agentic_loop")

        # 危险工具列表
        self._dangerous_tools = {"exec", "write", "edit"}

        # 状态
        self.state = LoopState()
        self.messages: list[dict] = []
        self.skills_loaded: dict[str, str] = {}
        self.logger.info(
            "AgenticLoop initialized | agent=%s workspace=%s max_iterations=%s",
            agent_name,
            workspace,
            max_iterations,
        )

    def _truncate_for_log(self, value: Any, limit: int = 300) -> str:
        return truncate_for_log(value, limit=limit)

    def _log_trace(self, stage: str, level: int = logging.INFO, **fields):
        self.logger.log(level, format_trace_message(stage, **fields))

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
                                self.logger.info("Skill loaded into context via explicit read: %s", skill_name)
                                self._log_trace("SKILL_LOADED", skill=skill_name, source="explicit_read", path=path)
                                return f"\n\n## Skill: {skill_name}\n\n{content}\n"
                # 检查是否是读取其他 skill 相关文件。这里必须匹配真正的 skills
                # 目录段，避免把 /itskill/... 之类的普通路径误判成技能目录。
                normalized_path = path.replace("\\", "/")
                skills_dir_normalized = str(skills_dir).replace("\\", "/").rstrip("/")
                inferred_skill_name = None

                if normalized_path.startswith(f"{skills_dir_normalized}/"):
                    relative_path = normalized_path[len(skills_dir_normalized) + 1:]
                    inferred_skill_name = relative_path.split("/", 1)[0]
                else:
                    match = re.search(r'(^|/)skills?/([A-Za-z0-9_-]+)(/|$)', normalized_path, re.IGNORECASE)
                    if match:
                        inferred_skill_name = match.group(2)

                if inferred_skill_name:
                    content = self.skill_loader.get_skill_content(inferred_skill_name)
                    if content:
                        self._print_skill_load(inferred_skill_name)
                        self.skills_loaded[inferred_skill_name] = content
                        self.logger.info("Skill loaded into context via inferred path: %s", inferred_skill_name)
                        self._log_trace("SKILL_LOADED", skill=inferred_skill_name, source="inferred_path", path=path)
                        return f"\n\n## Skill: {inferred_skill_name}\n\n{content}\n"

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
            self.logger.warning("Dangerous tool cancelled entire task | tool=%s", tool_name)
            return False, "", "用户取消任务", True, False
        if not confirmed:
            self.logger.warning("Dangerous tool execution rejected | tool=%s", tool_name)
            return False, "", "用户取消执行", False, False

        # 如果用户提供了补充提示，废弃当前 tool，让模型重新思考
        if hint:
            self.logger.info("Dangerous tool received user hint | tool=%s hint=%s", tool_name, self._truncate_for_log(hint))
            hint_message = {
                "role": "user",
                "content": f"【用户提示】刚才你打算执行 {tool_name} 工具，但我希望你在重新思考后给出更好的方案。我的补充意见是：{hint}\n\n请重新思考并决定下一步该怎么做。"
            }
            self.messages.append(hint_message)
            # 返回特殊状态：废弃当前 tool，让模型重新思考
            return True, "", None, False, True

        try:
            self.logger.info("Executing tool from loop | tool=%s args=%s", tool_name, self._truncate_for_log(args))
            result = self.tool_registry.execute(tool_name, args)
            if result.success:
                self.logger.info("Tool execution succeeded | tool=%s", tool_name)
                return True, result.content, None, False, False
            else:
                self.logger.warning("Tool execution failed | tool=%s error=%s", tool_name, self._truncate_for_log(result.error))
                return False, "", result.error, False, False
        except Exception as e:
            self.logger.exception("Tool execution raised exception | tool=%s", tool_name)
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

        self.logger.warning("Dangerous tool pending confirmation | tool=%s args=%s", tool_name, self._truncate_for_log(args))

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
                self.logger.info("Dangerous tool confirmed | tool=%s", tool_name)
                return True, "", False
            elif current == 1:
                # 取消执行（当前工具）
                print(f"{Colors.RED}✗ 已取消执行{Colors.RESET}")
                self.logger.warning("Dangerous tool rejected | tool=%s", tool_name)
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
                    self.logger.info("Dangerous tool confirmed with hint | tool=%s", tool_name)
                    return True, hint_text, False
                else:
                    print(f"{Colors.GREEN}✓ 无补充信息，执行中...{Colors.RESET}")
                    self.logger.info("Dangerous tool confirmed without additional hint | tool=%s", tool_name)
                    return True, "", False
            else:
                # 取消任务（结束整个对话）
                print(f"{Colors.YELLOW}⚠ 取消任务，结束对话...{Colors.RESET}")
                self.logger.warning("Dangerous tool cancelled task from confirmation menu | tool=%s", tool_name)
                return False, "", True

        except (EOFError, KeyboardInterrupt):
            print(f"\n{Colors.RED}✗ 已取消执行{Colors.RESET}")
            self.logger.warning("Dangerous tool confirmation interrupted | tool=%s", tool_name)
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
                logger=self.logger,
                workspace=self.workspace,
                **kwargs
            )
            self.logger.info("LLM returned | type=%s tool_calls=%s", response.get("type"), len(response.get("tool_calls") or []))
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
        """构建系统提示，默认优先走最短执行路径。"""
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
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 计算 memory 基础路径
        memory_base = self.workspace
        if not memory_base.endswith('/'):
            memory_base += '/'
        memory_base += 'memory'

        prompt_context = {
            "tool_descriptions": tool_descriptions,
            "skills_prompt": skills_prompt,
            "conversation_history": conversation_history,
            "current_time": current_time,
            "workspace": self.workspace,
            "agent_name": self.agent_name,
            "memory_base": memory_base,
            "agent_info": agent_info,
            "user_info": user_info,
            "soul_info": soul_info,
            "memory_info": memory_info,
        }

        external_prompt = self._load_external_system_prompt(prompt_context)
        if external_prompt:
            return external_prompt

        return self._build_default_system_prompt(prompt_context)

    def _load_external_system_prompt(self, context: dict[str, str]) -> Optional[str]:
        """从配置文件加载外部 system prompt 模板。"""
        agent_config = get_agent_config() or {}
        prompt_file = agent_config.get("system_prompt_file")
        if not prompt_file:
            return None

        prompt_path = Path(prompt_file)
        if not prompt_path.is_absolute():
            project_root = Path(__file__).resolve().parent.parent
            prompt_path = project_root / prompt_path

        if not prompt_path.exists():
            return None

        template = prompt_path.read_text(encoding="utf-8")
        return self._render_prompt_template(template, context)

    def _render_prompt_template(self, template: str, context: dict[str, str]) -> str:
        """渲染外部 prompt 模板，使用双大括号占位符。"""
        rendered = template
        for key, value in context.items():
            rendered = rendered.replace(f"{{{{{key}}}}}", value or "")
        return rendered

    def _build_default_system_prompt(self, context: dict[str, str]) -> str:
        """默认 system prompt，强调最短、最可靠的执行路径。"""
        parts = []

        parts.append("""# 你是 XiamiClaw Agent
你是一个在本地工作区执行任务的智能助手。默认目标是用最短、最可靠的路径完成用户请求，而不是展示完整思考过程。""")

        parts.append(f"""## 可用工具
工具名大小写敏感，只能调用真实存在的工具：
{context["tool_descriptions"]}""")

        parts.append("""## 最短路径原则
1. 能直接回答就直接回答，不调用工具。
2. 简单任务优先最短路径：先定位最相关文件或命令，再直接修改或执行。
3. 不要为了“更稳妥”而做无意义的额外读取、重复检查或拆分子任务。
4. 不要重复调用同一个失败工具，除非参数或策略已经改变。
5. 简单 coding/React/文件修改任务的目标是 1 到 3 次工具调用：
   - 一次定位
   - 一次修改
   - 必要时一次验证
6. 第一次读取如果已足够，就直接进入修改；不要继续扩散搜索。
7. 不要调用未在工具列表中的工具。""")

        parts.append("""## Tool 使用规则
- 默认不要叙述常规 tool 调用，直接执行。
- 只有在多步骤、风险较高或用户明确要求时，才简短说明进展。
- 涉及覆盖、删除、危险命令时，先提醒风险再执行。
- 简单任务不要生成子代理，不要过度任务分解。""")

        parts.append(f"""## Skills
先快速查看可用 skill 描述，再决定是否需要读取 SKILL.md。
- 只有当用户明确点名 skill，或某个 skill 与任务高度明确匹配时，才读取一个 SKILL.md。
- 普通 coding、React、小功能修改、文件编辑、命令执行，默认直接用工具，不要先读 skill。
- 一次最多预读一个 skill。

<available_skills>
{context["skills_prompt"]}
</available_skills>""")

        parts.append(f"""## Memory
- 只有当用户明确提到“上次做过什么”“记住这个”“我的偏好”“之前的决定”之类的历史信息时，才参考 memory。
- 普通当前任务不要先搜索或更新 memory。
- 不要假设存在 memory 专用工具；只能使用当前真实可用的工具。
- 如果用户明确要求记住信息，可在任务结束后再更新 `{context["memory_base"]}` 下相关文件。""")

        parts.append(f"""## 工作目录
当前工作目录：`{context["workspace"]}`
除非用户明确指定，否则文件操作默认在这里完成。""")

        parts.append(f"""## 当前时间
时区：Asia/Shanghai
当前时间：{context["current_time"]}""")

        if context["conversation_history"]:
            parts.append(f"""## 当前对话历史
{context["conversation_history"]}""")

        if context["soul_info"]:
            parts.append(f"""## SOUL.md
{context["soul_info"]}""")

        if context["agent_info"]:
            parts.append(f"""## AGENT.md
{context["agent_info"]}""")

        if context["user_info"]:
            parts.append(f"""## USER.md
{context["user_info"]}""")

        if context["memory_info"]:
            parts.append(f"""## MEMORY.md
{context["memory_info"]}""")

        parts.append("""## 回复方式
- 先给结果，再补充必要细节。
- 除非用户要求，不要展开冗长过程说明。
- 如果任务未完成，明确卡点和下一步最小动作。""")

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
        try:
            # 初始化状态
            self.state = LoopState(start_time=time.time())
            self.messages = []
            self.skills_loaded = {}

            # 创建新 session 并记录用户消息
            session_id = self.session_manager.create_session(user_message)
            self.session_manager.add_user_message(user_message)
            self.logger.info(
                "Agent loop started | session=%s message=%s",
                session_id,
                self._truncate_for_log(user_message),
            )
            self._log_trace(
                "RUN_START",
                session=session_id,
                user_input=summarize_for_log(user_message),
                max_iterations=self.max_iterations,
                max_tool_calls_per_iteration=self.max_tool_calls_per_iteration,
            )

            # 构建初始消息
            system_prompt = self._build_system_prompt()
            self.messages.append({"role": "system", "content": system_prompt})
            self.messages.append({"role": "user", "content": user_message})
            self.logger.info("System prompt built | length=%s", len(system_prompt))
            self._log_trace("SYSTEM_PROMPT_READY", session=session_id, prompt_length=len(system_prompt))

            # 获取工具列表
            tools = self._format_tools()
            self.logger.info("Tool catalog prepared | count=%s", len(tools))
            self._log_trace("TOOL_CATALOG_READY", session=session_id, tool_count=len(tools))

            # 记录开始时间
            start_time = time.time()
            # ReAct 循环
            while self._should_continue(self.state.iteration):
                self.state.iteration += 1
                self.logger.info(
                    "Iteration started | iteration=%s tool_calls=%s messages=%s",
                    self.state.iteration,
                    self.state.tool_calls,
                    len(self.messages),
                )
                self._log_trace(
                    "ITERATION_START",
                    session=session_id,
                    iteration=self.state.iteration,
                    total_tool_calls=self.state.tool_calls,
                    message_count=len(self.messages),
                )

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
                        self._log_trace(
                            "MODEL_REQUEST",
                            session=session_id,
                            iteration=self.state.iteration,
                            message_count=len(self.messages),
                            tool_count=len(tools),
                            latest_user_input=summarize_for_log(user_message),
                        )
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
                self.logger.info(
                    "LLM response parsed | type=%s content_length=%s tool_calls=%s",
                    response.get("type"),
                    len(response.get("content", "") or ""),
                    len(tool_calls),
                )
                self._log_trace(
                    "MODEL_DECISION",
                    session=session_id,
                    iteration=self.state.iteration,
                    response_type=response.get("type"),
                    selected_tools=",".join(tc.name for tc in tool_calls) if tool_calls else "none",
                    response_preview=summarize_for_log(response.get("content", "")),
                )

                if not tool_calls:
                    # 没有工具调用，返回响应
                    content = response.get("content", "")

                    self.messages.append({"role": "assistant", "content": content})

                    # 记录到 session
                    self.session_manager.add_assistant_message(content=content)
                    self.logger.info("Loop finished with direct response | session=%s content_length=%s", session_id, len(content or ""))
                    self._log_trace(
                        "FINAL_RESPONSE",
                        session=session_id,
                        iteration=self.state.iteration,
                        total_tool_calls=self.state.tool_calls,
                        reply=summarize_for_log(content),
                    )

                    yield Event(EventType.FINAL_RESPONSE, content)
                    return content

                # 处理工具调用
                for tool_call in tool_calls[:self.max_tool_calls_per_iteration]:
                    tool_name = tool_call.name
                    tool_args = tool_call.arguments
                    self.logger.info(
                        "Tool call received | tool=%s args=%s call_id=%s",
                        tool_name,
                        self._truncate_for_log(tool_args),
                        tool_call.call_id,
                    )
                    self._log_trace(
                        "TOOL_SELECTED",
                        session=session_id,
                        iteration=self.state.iteration,
                        call_id=tool_call.call_id,
                        tool=tool_name,
                        args=summarize_for_log(tool_args),
                    )

                    # 检查循环
                    is_loop, loop_count = self._detect_loop(tool_name, tool_args)

                    if show_progress:
                        yield Event(EventType.TOOL_CALL, {"name": tool_name, "args": tool_args})

                    if is_loop:
                        self.logger.warning("Loop suspicion detected | tool=%s count=%s", tool_name, loop_count)
                        if loop_count >= self.loop_max_threshold:
                            if show_progress:
                                self._print_loop_blocked(tool_name)

                            # 阻止执行并返回错误消息
                            error_msg = f"检测到循环调用: 工具 `{tool_name}` 被连续调用 {loop_count} 次。"
                            self.messages.append({
                                "role": "assistant",
                                "content": error_msg
                            })
                            self.logger.error("Loop blocked execution | tool=%s count=%s", tool_name, loop_count)
                            self._log_trace(
                                "TOOL_EXECUTION",
                                level=logging.ERROR,
                                session=session_id,
                                iteration=self.state.iteration,
                                call_id=tool_call.call_id,
                                tool=tool_name,
                                status="blocked_loop_detection",
                                detail=error_msg,
                            )

                            yield Event(EventType.ERROR, error_msg)
                            yield Event(EventType.FINAL_RESPONSE, error_msg)
                            return error_msg
                        else:
                            if show_progress:
                                self._print_loop_warning(tool_name, loop_count)

                    # 检查是否需要加载 skill
                    skill_content = self._check_and_load_skill(tool_call=tool_call)
                    if skill_content:
                        if show_progress:
                            print(f"\n{Colors.GREEN}已加载 skill 内容到上下文{Colors.RESET}")
                        # 将 skill 内容添加到上下文。消息角色的 provider 兼容性由
                        # models/custom.py 的标准化逻辑统一处理。
                        self.messages.append({
                            "role": "system",
                            "content": f"## 加载的 Skill 内容\n{skill_content}"
                        })

                    # 参数校验：参数异常不执行工具，直接反馈给模型重试
                    arg_error = self._validate_tool_args(tool_name, tool_args)
                    if arg_error:
                        self.logger.warning("Tool argument validation failed | tool=%s error=%s", tool_name, arg_error)
                        self._log_trace(
                            "TOOL_EXECUTION",
                            level=logging.WARNING,
                            session=session_id,
                            iteration=self.state.iteration,
                            call_id=tool_call.call_id,
                            tool=tool_name,
                            status="invalid_arguments",
                            detail=arg_error,
                        )
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
                    tool_exec_started = time.time()
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
                        self.logger.warning("Loop cancelled by user during tool execution | tool=%s", tool_name)
                        self._log_trace(
                            "TOOL_EXECUTION",
                            level=logging.WARNING,
                            session=session_id,
                            iteration=self.state.iteration,
                            call_id=tool_call.call_id,
                            tool=tool_name,
                            status="cancelled_by_user",
                            duration_ms=int((time.time() - tool_exec_started) * 1000),
                        )
                        yield Event(EventType.ERROR, "用户取消任务")
                        yield Event(EventType.FINAL_RESPONSE, None)
                        return None

                    # 如果废弃当前 tool，让模型重新思考
                    if discard:
                        self.logger.info("Tool discarded for replanning | tool=%s", tool_name)
                        self._log_trace(
                            "TOOL_EXECUTION",
                            session=session_id,
                            iteration=self.state.iteration,
                            call_id=tool_call.call_id,
                            tool=tool_name,
                            status="discarded_for_replanning",
                            duration_ms=int((time.time() - tool_exec_started) * 1000),
                        )
                        if show_progress:
                            print(f"{Colors.YELLOW}⚠ 已废弃当前工具，等待模型重新思考...{Colors.RESET}")
                        # 不记录到历史，不添加 tool 结果，继续下一个 tool 或重新循环
                        continue

                    if show_progress:
                        yield Event(EventType.TOOL_RESULT, {"success": success, "content": content, "error": error})
                    self.logger.info(
                        "Tool result recorded | tool=%s success=%s error=%s",
                        tool_name,
                        success,
                        self._truncate_for_log(error),
                    )
                    self._log_trace(
                        "TOOL_EXECUTION",
                        level=logging.INFO if success else logging.WARNING,
                        session=session_id,
                        iteration=self.state.iteration,
                        call_id=tool_call.call_id,
                        tool=tool_name,
                        status="success" if success else "failed",
                        duration_ms=int((time.time() - tool_exec_started) * 1000),
                        result_summary=summarize_tool_result(success, content=content, error=error),
                    )

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
                    self._log_trace(
                        "ITERATION_END",
                        session=session_id,
                        iteration=self.state.iteration,
                        total_tool_calls=self.state.tool_calls,
                        last_tool=tool_name,
                    )

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
            self.logger.warning(
                "Loop reached max iterations | elapsed=%.2fs tool_calls=%s",
                elapsed,
                self.state.tool_calls,
            )
            self._log_trace(
                "RUN_STOPPED",
                level=logging.WARNING,
                session=session_id,
                reason="max_iterations_reached",
                elapsed_ms=int(elapsed * 1000),
                total_tool_calls=self.state.tool_calls,
                reply=summarize_for_log(final_response),
            )

            yield Event(EventType.ERROR, "达到最大迭代")
            yield Event(EventType.FINAL_RESPONSE, final_response)
            return final_response
        except Exception:
            self.logger.exception("Agent loop failed unexpectedly")
            raise


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
