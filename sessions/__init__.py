"""
Session 管理模块

参考 OpenClaw 的 session 管理方式，存储对话历史：
- 使用 JSONL 格式存储每个 session 的对话
- 支持多个 session
- 自动保存对话历史
"""

import json
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field, asdict


@dataclass
class Message:
    """对话消息"""
    role: str  # user, assistant, tool, system
    content: Any = None
    tool_call: Optional[dict] = None
    tool_call_id: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class SessionMetadata:
    """Session 元数据"""
    id: str
    created_at: str
    updated_at: str
    user_message: str = ""
    message_count: int = 0


class SessionManager:
    """Session 管理器"""

    def __init__(self, sessions_dir: str = None, logger=None):
        """
        初始化 Session 管理器

        Args:
            sessions_dir: sessions 目录路径，默认为 workspace/sessions
        """
        if sessions_dir is None:
            # 默认使用 workspace/sessions 文件夹
            current_dir = Path(__file__).parent.parent
            sessions_dir = current_dir / "workspace" / "sessions"

        self.sessions_dir = Path(sessions_dir)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logger or logging.getLogger("xiamiclaw.sessions")

        # 当前活跃的 session
        self.current_session_id: Optional[str] = None
        self.current_session_path: Optional[Path] = None

        # 会话历史（内存中）
        self.messages: list[dict] = []

    def create_session(self, user_message: str = "", force_new: bool = False) -> str:
        """
        创建或复用 session

        Args:
            user_message: 用户的第一条消息（仅在新 session 时使用）
            force_new: 是否强制创建新 session（默认 False，会复用现有 session）

        Returns:
            session_id
        """
        # 如果不是强制创建新 session，且已有活跃 session，则复用
        if not force_new and self.current_session_id and self.current_session_path:
            # 复用现有 session，直接返回 ID，让调用者决定是否添加消息
            self.logger.info("Reusing existing session: %s", self.current_session_id)
            return self.current_session_id

        # 生成 session ID
        session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # 创建 session 文件
        session_file = self.sessions_dir / f"{session_id}.jsonl"

        # 写入元数据
        metadata = {
            "type": "session",
            "id": session_id,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "user_message": user_message,
        }
        with open(session_file, 'w', encoding='utf-8') as f:
            f.write(json.dumps(metadata, ensure_ascii=False) + "\n")

        # 设置为当前 session
        self.current_session_id = session_id
        self.current_session_path = session_file
        self.messages = []
        self.logger.info("Created session: %s", session_id)

        return session_id

    def add_message(self, role: str, content: Any = None, tool_call: dict = None, tool_call_id: str = None):
        """
        添加消息到当前 session

        Args:
            role: 角色 (user, assistant, tool, system)
            content: 消息内容
            tool_call: 工具调用信息
            tool_call_id: 工具调用 ID
        """
        if not self.current_session_id:
            # 如果没有 session，创建一个
            self.create_session()

        message = {
            "role": role,
            "timestamp": datetime.now().isoformat(),
        }

        if content is not None:
            message["content"] = content

        if tool_call:
            message["tool_call"] = tool_call

        if tool_call_id:
            message["tool_call_id"] = tool_call_id

        # 添加到内存
        self.messages.append(message)

        # 持久化到文件
        self._persist_message(message)
        self.logger.debug("Appended session message: role=%s session=%s", role, self.current_session_id)

    def add_user_message(self, content: str):
        """添加用户消息"""
        self.add_message(role="user", content=content)

    def add_assistant_message(self, content: str = None, tool_calls: list = None):
        """添加助手消息"""
        if tool_calls:
            for tc in tool_calls:
                self.add_message(
                    role="assistant",
                    content=content,
                    tool_call=tc.get("function"),
                    tool_call_id=tc.get("id")
                )
        else:
            self.add_message(role="assistant", content=content)

    def add_tool_result(self, tool_call_id: str, content: str):
        """添加工具结果"""
        self.add_message(role="tool", content=content, tool_call_id=tool_call_id)

    def add_system_message(self, content: str):
        """添加系统消息"""
        self.add_message(role="system", content=content)

    def _persist_message(self, message: dict):
        """持久化消息到文件"""
        if not self.current_session_path:
            return

        with open(self.current_session_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(message, ensure_ascii=False) + "\n")

        # 更新元数据
        self._update_metadata()

    def _update_metadata(self):
        """更新 session 元数据"""
        if not self.current_session_path or not self.current_session_path.exists():
            return

        # 读取现有内容
        try:
            with open(self.current_session_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            if not lines:
                return

            # 解析第一行（metadata）
            metadata = json.loads(lines[0])
            metadata["updated_at"] = datetime.now().isoformat()
            metadata["message_count"] = len(self.messages)

            # 写回
            with open(self.current_session_path, 'w', encoding='utf-8') as f:
                f.write(json.dumps(metadata, ensure_ascii=False) + "\n")
                # 写入剩余的消息
                for line in lines[1:]:
                    f.write(line)
        except:
            self.logger.exception("Failed to update session metadata: %s", self.current_session_path)

    def get_session_messages(self, session_id: str = None) -> list[dict]:
        """
        获取 session 的所有消息

        Args:
            session_id: session ID，如果为 None 则获取当前 session

        Returns:
            消息列表
        """
        if session_id is None:
            session_id = self.current_session_id

        if not session_id:
            return []

        session_file = self.sessions_dir / f"{session_id}.jsonl"

        if not session_file.exists():
            return []

        messages = []
        try:
            with open(session_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    msg = json.loads(line)
                    # 跳过 metadata
                    if msg.get("type") == "session":
                        continue
                    messages.append(msg)
        except:
            self.logger.exception("Failed to read session messages: %s", session_file)

        return messages

    def get_recent_messages(self, count: int = 10, session_id: str = None) -> list[dict]:
        """获取最近 N 条消息"""
        all_messages = self.get_session_messages(session_id)
        return all_messages[-count:] if all_messages else []

    def list_sessions(self) -> list[dict]:
        """列出所有 sessions"""
        sessions = []

        for session_file in self.sessions_dir.glob("*.jsonl"):
            try:
                with open(session_file, 'r', encoding='utf-8') as f:
                    first_line = f.readline()
                    if first_line:
                        metadata = json.loads(first_line)
                        if metadata.get("type") == "session":
                            sessions.append(metadata)
            except:
                self.logger.exception("Failed to list session file: %s", session_file)
                continue

        # 按更新时间排序
        sessions.sort(key=lambda x: x.get("updated_at", ""), reverse=True)

        return sessions

    def load_session(self, session_id: str):
        """加载指定 session"""
        session_file = self.sessions_dir / f"{session_id}.jsonl"

        if not session_file.exists():
            return False

        self.current_session_id = session_id
        self.current_session_path = session_file
        self.messages = self.get_session_messages(session_id)
        self.logger.info("Loaded session: %s", session_id)

        return True

    def get_current_session_id(self) -> Optional[str]:
        """获取当前 session ID"""
        return self.current_session_id

    def format_conversation_for_llm(self, max_messages: int = 20) -> str:
        """
        格式化对话历史供 LLM 使用

        Args:
            max_messages: 最大消息数

        Returns:
            格式化的对话字符串
        """
        messages = self.get_recent_messages(max_messages)

        if not messages:
            return ""

        lines = ["## 对话历史\n"]
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            if role == "user":
                lines.append(f"**用户**: {content}")
            elif role == "assistant":
                lines.append(f"**助手**: {content}")
            elif role == "tool":
                lines.append(f"**工具结果**: {content[:200]}...")
            elif role == "system":
                lines.append(f"**系统**: {content[:100]}...")

            lines.append("")

        return "\n".join(lines)


# 全局 session 管理器
_session_manager: Optional[SessionManager] = None


def get_session_manager(sessions_dir: str = None) -> SessionManager:
    """获取全局 Session 管理器实例"""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager(sessions_dir)
    return _session_manager


# 便捷函数
def create_session(user_message: str = "") -> str:
    """创建新 session"""
    return get_session_manager().create_session(user_message)


def add_user_message(content: str):
    """添加用户消息"""
    get_session_manager().add_user_message(content)


def add_assistant_message(content: str = None, tool_calls: list = None):
    """添加助手消息"""
    get_session_manager().add_assistant_message(content, tool_calls)


def add_tool_result(tool_call_id: str, content: str):
    """添加工具结果"""
    get_session_manager().add_tool_result(tool_call_id, content)


def get_conversation_history(max_messages: int = 20) -> list[dict]:
    """获取对话历史"""
    return get_session_manager().get_recent_messages(max_messages)


def format_conversation_for_llm(max_messages: int = 20) -> str:
    """格式化对话历史"""
    return get_session_manager().format_conversation_for_llm(max_messages)
