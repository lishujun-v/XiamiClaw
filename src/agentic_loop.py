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
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional

# 导入 memory 模块
from memory import (
    format_memory_context,
    get_memory_manager,
)
from sessions import (
    get_session_manager,
    create_session,
    add_user_message,
    add_assistant_message,
    add_tool_result,
    format_conversation_for_llm,
)


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
        """
        self.llm_provider = llm_provider
        self.tool_registry = tool_registry
        self.skill_loader = skill_loader

        # Memory 管理器
        self.memory_manager = get_memory_manager()

        self.max_iterations = max_iterations
        self.max_tool_calls_per_iteration = max_tool_calls_per_iteration
        self.enable_loop_detection = enable_loop_detection
        self.loop_warning_threshold = loop_warning_threshold
        self.loop_max_threshold = loop_max_threshold

        # 状态
        self.state = LoopState()
        self.messages: list[dict] = []
        self.skills_loaded: dict[str, str] = {}

        # Memory 管理器
        self.memory_manager = get_memory_manager()

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

    def _check_and_load_skill(self, tool_call: ToolCall = None, last_message: str = None) -> Optional[str]:
        """
        检查是否需要加载 skill 并加载

        流程：
        1. 如果模型调用了 read 工具读取某个 skill 的 SKILL.md，直接返回内容
        2. 如果模型在消息中提到要使用某个 skill，加载该 skill 的完整内容

        Args:
            tool_call: 工具调用（如果有）
            last_message: 最后的助手消息（如果有）

        Returns:
            加载的 skill 内容，如果没有则返回 None
        """
        # 方式1: 通过 tool_call 检测（模型读取 skill 文件）
        if tool_call:
            tool_name = tool_call.name
            args = tool_call.arguments

            if tool_name == "read":
                path = args.get("path", "") or args.get("file_path", "")
                # 检查是否是读取 skill 文件
                for skill_entry in self.skill_loader.get_all_skills():
                    skill_name = skill_entry.skill.name if hasattr(skill_entry, 'skill') else None
                    if not skill_name:
                        continue
                    skill_path = f"skills/{skill_name}/SKILL.md"
                    if skill_path in path or f"skills/{skill_name}" in path:
                        self._print_skill_load(skill_name)
                        content = self.skill_loader.get_skill_content(skill_name)
                        if content:
                            self.skills_loaded[skill_name] = content
                            return f"\n\n## Skill: {skill_name}\n\n{content}\n"
                # 检查是否是读取其他 skill 相关文件
                if "skill" in path.lower() or "SKILL" in path:
                    # 尝试提取 skill 名称
                    match = re.search(r'(?:skills?[/\\]?|SKILL\.md[/\\]?)(\w+)', path, re.IGNORECASE)
                    if match:
                        skill_name = match.group(1)
                        self._print_skill_load(skill_name)
                        content = self.skill_loader.get_skill_content(skill_name)
                        if content:
                            self.skills_loaded[skill_name] = content
                            return f"\n\n## Skill: {skill_name}\n\n{content}\n"

        # 方式2: 检测消息中是否提到使用某个 skill
        if last_message:
            msg_lower = last_message.lower()
            for skill_entry in self.skill_loader.get_all_skills():
                skill_name = skill_entry.skill.name if hasattr(skill_entry, 'skill') else None
                if not skill_name:
                    continue

                # 检测关键词：使用/调用/执行 + skill 名称
                patterns = [
                    f"使用{skill_name}",
                    f"调用{skill_name}",
                    f"执行{skill_name}",
                    f"use {skill_name}",
                    f"call {skill_name}",
                    f"execute {skill_name}",
                ]

                if any(p.lower() in msg_lower for p in patterns):
                    # 检查是否已经加载过
                    if skill_name in self.skills_loaded:
                        return None

                    self._print_skill_load(skill_name)
                    content = self.skill_loader.get_skill_content(skill_name)
                    if content:
                        self.skills_loaded[skill_name] = content
                        return f"\n\n## Skill: {skill_name}\n\n{content}\n"

        return None

    def _execute_tool(self, tool_name: str, args: dict) -> tuple[bool, str, Optional[str]]:
        """
        执行工具

        Args:
            tool_name: 工具名称
            args: 工具参数

        Returns:
            (成功标志, 内容, 错误信息)
        """
        if not self.tool_registry:
            return False, "", "工具注册表未初始化"

        try:
            result = self.tool_registry.execute(tool_name, args)
            if result.success:
                return True, result.content, None
            else:
                return False, "", result.error
        except Exception as e:
            return False, "", str(e)

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

    def _call_llm(
        self,
        messages: list[dict],
        tools: list[dict] = None,
        **kwargs
    ) -> dict:
        """调用 LLM"""
        if self.llm_provider:
            return self.llm_provider(messages, tools, **kwargs)
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

                # 如果是字符串，尝试解析
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except:
                        arguments = {}

                tool_calls.append(ToolCall(
                    name=name,
                    arguments=arguments,
                    call_id=call.get("id", f"call_{len(tool_calls)}")
                ))

        return tool_calls

    def _build_system_prompt(self) -> str:
        """构建系统提示 - 参考 OpenClaw v3.9"""
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
        session_manager = get_session_manager()
        conversation_history = session_manager.format_conversation_for_llm(max_messages=10)

        # 获取当前时间
        from datetime import datetime
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 构建系统提示
        parts = []

        # === 1. 开场 ===
        parts.append("""You are a personal assistant running inside OpenClaw Agent.
你是一个运行在 OpenClaw Agent 中的个人助手。""")

        # === 2. 工具列表 (Tooling) ===
        parts.append(f"""## Tooling
工具可用性（按策略过滤）：
Tool names are case-sensitive. Call tools exactly as listed.

{tool_descriptions}

### Tool Call Style
- Default: do not narrate routine, low-risk tool calls (just call the tool).
- Narrate only when it helps: multi-step work, complex/challenging problems, sensitive actions (e.g., deletions), or when the user explicitly asks.
- Keep narration brief and value-dense; avoid repeating obvious steps.
- Use plain human language for narration unless in a technical context.
- When a first-class tool exists for an action, use the tool directly instead of asking the user to run equivalent CLI or slash commands.

### Reply Style (最终回复)
- 当工具执行完成后，给用户的最终回复要简洁明了
- 优先告知用户：任务是否成功、关键结果是什么
- 示例：
  - ✅ "好的，已创建文件 `/workspace/test.py` 并执行成功。当前时间是 2024-03-17 10:30:45"
  - ❌ "我来帮您完成这个任务。首先我使用了 write 工具创建了一个 Python 文件，这个文件包含了获取系统时间的代码..."
- 除非用户明确要求，否则不要详细描述执行过程
- 保留关键信息即可：文件路径、执行结果、关键输出

### Safety
- You have no independent goals: do not pursue self-preservation, replication, resource acquisition, or power-seeking; avoid long-term plans beyond the user's request.
- Prioritize safety and human oversight over completion; if instructions conflict, pause and ask.
- Do not manipulate or persuade anyone to expand access or disable safeguards.""")

        # === 3. Skills (mandatory) ===
        parts.append(f"""## Skills (mandatory)
Before replying: scan <available_skills> <description> entries.
- If exactly one skill clearly applies: read its SKILL.md at <location> with `read`, then follow it.
- If multiple could apply: choose the most specific one, then read/follow it.
- If none clearly apply: do not read any SKILL.md.
- Constraints: never read more than one skill up front; only read after selecting.
- When a skill drives external API writes, assume rate limits: prefer fewer larger writes, avoid tight one-item loops, serialize bursts when possible, and respect 429/Retry-After.
The following skills provide specialized instructions for specific tasks.
Use the read tool to load a skill's file when the task matches its description.

<available_skills>
{skills_prompt}
</available_skills>""")

        # === 4. Memory Recall ===
        parts.append("""## Memory Recall
Before answering anything about prior work, decisions, dates, people, preferences, or todos: use memory_search to search MEMORY.md + memory/*.md; then use memory_get to pull only the needed lines.
Citations: include Source: <path#line> when it helps the user verify memory snippets.""")

        # === 5. Session History ===
        if conversation_history:
            parts.append(f"""## Current Conversation History
{conversation_history}""")

        # === 6. Identity & Context ===
        if soul_info:
            parts.append(f"""## SOUL.md - Who You Are
{soul_info}""")

        if agent_info:
            parts.append(f"""## AGENT.md - Your Identity
{agent_info}""")

        if user_info:
            parts.append(f"""## USER.md - About Your Human
{user_info}""")

        # === 7. Long-term Memory ===
        if memory_info:
            parts.append(f"""## MEMORY.md - Long-term Memory
{memory_info}""")

        # === 8. Workspace ===
        parts.append("""## Workspace
Your working directory is: ./workspace
Treat this directory as the single global workspace for file operations unless explicitly instructed otherwise.""")

        # === 9. Current Date & Time ===
        parts.append(f"""## Current Date & Time
Time zone: Asia/Shanghai
Current time: {current_time}""")

        # === 10. ReAct Pattern ===
        parts.append("""## Execution Pattern - ReAct
按以下步骤思考和执行：
1. Think (思考): 分析任务并规划方法
2. Action (行动): 执行适当的工具
3. Observe (观察): 检查结果
4. Reflect (反思): 如需要则调整方法

Remember: You can use tools to help complete the user's request. When you need to execute commands, use the exec tool.

### Memory Management (重要!)
只有在用户明确提供了重要信息时才需要保存：

**需要保存的情况（谨慎判断）：**
- 用户明确告诉了自己的名字（如"我叫张三"、"你可以叫我小张"）
- 用户明确说明了偏好或习惯（如"我喜欢用 Python"、"我习惯用 tabs"）
- 用户或 Agent 明确了重要的决定或约定
- 重要的客观事实（如项目结构、重要配置）

**不需要保存的情况：**
- 日常寒暄、闲聊
- 琐碎的对话细节
- 不确定的信息

**保存步骤（必须按顺序）：**
1. 先用 read 工具读取对应的 memory 文件
2. 分析现有内容，决定是新增、修改还是跳过
3. 如果要更新，使用 write 工具写入完整内容（不要覆盖原有重要信息）""")

        # === 11. Start ===
        parts.append("""## Start
现在，请帮助用户完成他们的请求。
Now, please help the user with their request.""")

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

        lines = []
        for skill_entry in all_skills:
            try:
                # 尝试获取 skill 信息
                if hasattr(skill_entry, 'skill'):
                    name = skill_entry.skill.name
                    description = skill_entry.skill.description
                    location = f"skills/{name}/SKILL.md"
                else:
                    # 备用方式
                    skill_dict = skill_entry if isinstance(skill_entry, dict) else {}
                    name = skill_dict.get('skill', {}).get('name', 'unknown')
                    description = skill_dict.get('skill', {}).get('description', '')
                    location = f"skills/{name}/SKILL.md"

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

    def _auto_save_memory(self, user_message: str, final_response: str, show_progress: bool = True) -> bool:
        """
        自动判断并保存重要信息到 memory（智能追加而非覆盖）

        Args:
            user_message: 用户消息
            final_response: Agent 的最终回复
            show_progress: 是否显示进度

        Returns:
            是否保存了信息
        """
        # 构建提示，让 LLM 判断需要保存什么（极严格的判断标准）
        memory_prompt = f"""请分析以下对话，判断用户是否明确提供了必须记住的重要信息。

用户消息: {user_message}
Agent回复: {final_response}

【关键：什么信息存到什么文件 - 必须逐个分析用户消息中的每一句话】

USER.md（只存用户自己的信息）：
- 用户说"我叫xxx"、"我的名字是xxx" → 存用户名字到 USER.md
- 用户说"我喜欢xxx"、"我习惯用xxx" → 存用户偏好到 USER.md

AGENT.md（只存 Agent 的身份信息）：
- 用户给 Agent 命名："你叫xxx"、"你的名字是xxx"、"以后叫xxx" → 存 Agent 名字到 AGENT.md
- 用户定义 Agent 的角色："你是xxx助手" → 存 Agent 角色到 AGENT.md

SOUL.md（只存用户对 Agent 性格的期望）：
- 用户说"你要xxx性格"、"希望你是xxx风格" → 存到 SOUL.md

MEMORY.md（只存重要事实和决定）：
- 用户明确做了重要决定或约定

【重要：一句话可能包含多种信息！】

例如："我叫李李，你以后叫蟹酱吧"
- "我叫李李" → 用户名字 → 存到 USER.md → "名字: 李李"
- "你以后叫蟹酱" → 给 Agent 命名 → 存到 AGENT.md → "名字: 蟹酱"

【绝对不要存的情况】
- 日常寒暄、闲聊
- 用户只是问问题
- Agent 自己生成的回答

请严格按照以下 JSON 格式返回：
{{
    "save_user": "只有用户明确提供了自己的信息时才返回，如'名字: 李李'，否则为空''",
    "save_soul": "只有用户明确说了对Agent性格期望时才返回，如'性格: 活泼'，否则为空''",
    "save_agent": "只有用户给Agent命名或定义角色时才返回，如'名字: 蟹酱'，否则为空''",
    "save_memory": "只有用户做了重要决定时才返回，否则为空''"
}}

记住：绝大多数对话都不需要保存任何信息！"""

        try:
            # 调用 LLM 判断
            response = self._call_llm([
                {"role": "user", "content": memory_prompt}
            ], tools=None)

            content = response.get("content", "{}")

            # 尝试解析 JSON
            import json
            import re

            # 提取 JSON
            json_match = re.search(r'\{[\s\S]*\}', content)
            if not json_match:
                return False

            memory_data = json.loads(json_match.group())

            saved = False

            # 读取现有文件内容
            existing_user = self.memory_manager.get_user_memory()
            existing_soul = self.memory_manager.get_soul_memory()
            existing_agent = self.memory_manager.get_agent_memory()

            # 保存用户信息（智能追加）
            if memory_data.get("save_user") and memory_data["save_user"].strip():
                new_user_info = memory_data["save_user"].strip()
                # 检查是否已存在相同信息
                if new_user_info not in existing_user:
                    self._smart_append_memory("USER.md", new_user_info, existing_user)
                    if show_progress:
                        print(f"\n{Colors.GREEN}✓ 已更新用户信息到 USER.md{Colors.RESET}")
                    saved = True

            # 保存 Agent 性格信息（智能追加）
            if memory_data.get("save_soul") and memory_data["save_soul"].strip():
                new_soul_info = memory_data["save_soul"].strip()
                if new_soul_info not in existing_soul:
                    self._smart_append_memory("SOUL.md", new_soul_info, existing_soul)
                    if show_progress:
                        print(f"\n{Colors.GREEN}✓ 已更新 Agent 性格信息到 SOUL.md{Colors.RESET}")
                    saved = True

            # 保存 Agent 角色信息（智能追加）
            if memory_data.get("save_agent") and memory_data["save_agent"].strip():
                new_agent_info = memory_data["save_agent"].strip()
                if new_agent_info not in existing_agent:
                    self._smart_append_memory("AGENT.md", new_agent_info, existing_agent)
                    if show_progress:
                        print(f"\n{Colors.GREEN}✓ 已更新 Agent 角色信息到 AGENT.md{Colors.RESET}")
                    saved = True

            # 保存重要事实到 MEMORY.md
            if memory_data.get("save_memory") and memory_data["save_memory"].strip():
                self.memory_manager.append_longterm_memory(memory_data["save_memory"].strip())
                if show_progress:
                    print(f"\n{Colors.GREEN}✓ 已保存重要信息到 MEMORY.md{Colors.RESET}")
                saved = True

            return saved

        except Exception as e:
            if show_progress:
                print(f"\n{Colors.DIM}自动保存记忆失败: {str(e)}{Colors.RESET}")
            return False

    def _smart_append_memory(self, file_name: str, new_content: str, existing_content: str):
        """
        智能更新 memory 内容（直接修改模板中的占位符，不追加）

        Args:
            file_name: 文件名
            new_content: 新内容（如 "名字: 蟹酱"）
            existing_content: 现有内容
        """
        import re

        # 解析新内容，提取 key 和 value
        # 例如 "名字: 蟹酱" -> key="名字", value="蟹酱"
        match = re.match(r'^([^:]+):\s*(.+)$', new_content.strip())
        if not match:
            # 如果格式不对，直接跳过
            return

        key = match.group(1).strip()
        value = match.group(2).strip()

        # 查找模板中的占位符，支持多种格式：
        # - "名字: [待命名]"
        # - "- 名字: [待命名]"
        # - "- **名字**: [待命名]"
        # 替换为新值
        pattern = rf'^(\s*[-*]?\s*[\*]*\s*{re.escape(key)}[\*]*\s*:\s*).*$'
        replacement = rf'\1{value}'

        # 多行匹配替换
        final_content, count = re.subn(pattern, replacement, existing_content, flags=re.MULTILINE)

        if count == 0:
            # 如果没找到要替换的项，在 "基本信息" 或 "用户基本信息" section 下添加
            section_pattern = r'^(##\s+(?:基本信息|用户基本信息|性格特点|行为风格|沟通方式|偏好|核心能力|职责|使用约束))'
            if re.search(section_pattern, final_content, re.MULTILINE):
                # 在第一个 section 下添加（使用无序列表格式）
                final_content = re.sub(
                    section_pattern,
                    rf'\1\n- {key}: {value}',
                    final_content,
                    count=1,
                    flags=re.MULTILINE
                )

        self.memory_manager.update_memory_file(file_name, final_content, append=False)

        self.memory_manager.update_memory_file(file_name, final_content, append=False)

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
    ) -> str:
        """
        运行 Agentic Loop

        Args:
            user_message: 用户消息
            show_progress: 是否显示进度

        Returns:
            最终响应
        """
        if show_progress:
            self._print_header("Agentic Loop 启动")

        # 初始化状态
        self.state = LoopState(start_time=time.time())
        self.messages = []
        self.skills_loaded = {}

        # 创建新 session 并记录用户消息
        session_manager = get_session_manager()
        session_id = session_manager.create_session(user_message)
        session_manager.add_user_message(user_message)

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
                self._print_iteration(self.state.iteration, self.max_iterations)

            # 调用 LLM
            if show_progress:
                self._print_thinking()

            response = self._call_llm(self.messages, tools=tools)

            # 解析工具调用
            tool_calls = self._parse_tool_calls(response)

            # 检测是否在消息中提到要使用某个 skill
            assistant_message = response.get("content", "")
            skill_content = self._check_and_load_skill(last_message=assistant_message)
            if skill_content:
                if show_progress:
                    print(f"\n{Colors.GREEN}检测到使用 Skill，已加载内容到上下文{Colors.RESET}")
                self.messages.append({
                    "role": "system",
                    "content": f"## 加载的 Skill 内容\n{skill_content}"
                })

            if not tool_calls:
                # 没有工具调用，返回响应
                content = response.get("content", "")
                self.messages.append({"role": "assistant", "content": content})

                # 记录到 session
                session_manager = get_session_manager()
                session_manager.add_assistant_message(content=content)

                if show_progress:
                    self._print_final_response(content)

                # 自动保存记忆
                self._auto_save_memory(user_message, content, show_progress)

                return content

            # 处理工具调用
            for tool_call in tool_calls[:self.max_tool_calls_per_iteration]:
                tool_name = tool_call.name
                tool_args = tool_call.arguments

                # 检查循环
                is_loop, loop_count = self._detect_loop(tool_name, tool_args)

                if show_progress:
                    self._print_tool_call(tool_name, tool_args)

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

                        # 自动保存记忆
                        self._auto_save_memory(user_message, error_msg, show_progress)

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

                # 执行工具
                success, content, error = self._execute_tool(tool_name, tool_args)

                if show_progress:
                    self._print_tool_result(success, content, error)

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
                session_manager = get_session_manager()
                session_manager.add_assistant_message(
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
                session_manager.add_tool_result(tool_call_id=tool_call.call_id, content=result_content)

        # 达到最大迭代
        elapsed = time.time() - start_time

        if show_progress:
            self._print_header(f"达到最大迭代 ({self.max_iterations})")
            print(f"{Colors.YELLOW}总耗时: {elapsed:.1f}s, 工具调用: {self.state.tool_calls}{Colors.RESET}")

        final_response = ("我已尽最大努力处理您的请求，但尚未完成。"
                "您可以提供更多细节或重新描述您的问题。")

        # 自动保存记忆
        self._auto_save_memory(user_message, final_response, show_progress)

        return final_response


def create_agentic_loop(
    llm_provider: Optional[Callable] = None,
    tool_registry: Optional[Any] = None,
    skill_loader: Optional[Any] = None,
    **kwargs
) -> AgenticLoop:
    """
    创建 Agentic Loop 实例

    Args:
        llm_provider: LLM 提供者
        tool_registry: 工具注册表
        skill_loader: Skill 加载器
        **kwargs: 其他参数

    Returns:
        AgenticLoop 实例
    """
    return AgenticLoop(
        llm_provider=llm_provider,
        tool_registry=tool_registry,
        skill_loader=skill_loader,
        **kwargs
    )


# 便捷函数
def run_agentic_loop(
    user_message: str,
    llm_provider: Optional[Callable] = None,
    tool_registry: Optional[Any] = None,
    skill_loader: Optional[Any] = None,
    show_progress: bool = True,
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
        **kwargs: 其他参数

    Returns:
        最终响应
    """
    loop = create_agentic_loop(
        llm_provider=llm_provider,
        tool_registry=tool_registry,
        skill_loader=skill_loader,
        **kwargs
    )

    return loop.run(user_message, show_progress=show_progress)
