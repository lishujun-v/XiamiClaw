"""
Memory Management Module

提供类似 OpenClaw 的 memory 管理功能：
- 预加载 memory 文件
- 执行完成后更新记忆
- 语义搜索功能（可选）
"""

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional


class MemoryManager:
    """记忆管理器"""

    def __init__(self, memory_dir: Optional[str] = None):
        """
        初始化记忆管理器

        Args:
            memory_dir: memory 目录路径，默认为 workspace/memory 文件夹
        """
        if memory_dir is None:
            # 默认使用 workspace/memory 文件夹
            current_dir = Path(__file__).parent.parent
            memory_dir = current_dir / "workspace" / "memory"

        self.memory_dir = Path(memory_dir)
        self.agent_file = self.memory_dir / "AGENT.md"
        self.user_file = self.memory_dir / "USER.md"
        self.soul_file = self.memory_dir / "SOUL.md"
        self.memory_file = self.memory_dir / "MEMORY.md"
        self.daily_dir = self.memory_dir / "daily"

    def _ensure_memory_dir(self):
        """确保 memory 目录存在并创建模板文件"""
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.daily_dir.mkdir(parents=True, exist_ok=True)

        # 创建模板文件（如果不存在）
        self._create_template_if_not_exists(self.agent_file, self._get_agent_template())
        self._create_template_if_not_exists(self.user_file, self._get_user_template())
        self._create_template_if_not_exists(self.soul_file, self._get_soul_template())
        self._create_template_if_not_exists(self.memory_file, self._get_memory_template())

    def _create_template_if_not_exists(self, file_path: Path, template: str):
        """如果文件不存在，创建模板文件"""
        if not file_path.exists():
            file_path.write_text(template, encoding="utf-8")

    def _get_agent_template(self) -> str:
        """获取 AGENT.md 模板"""
        return f"""# AGENT.md

> file_path: {self.agent_file}

> 关于 agent 身份的信息

## 基本信息
- **姓名**: [待填写]
- **角色**: [待填写]
- **创建时间**: [待填写]

## 能力
- [待填写]

## 已知信息
- [待填写]

## 备注
- [待填写]
"""

    def _get_user_template(self) -> str:
        """获取 USER.md 模板"""
        return f"""# USER.md

> file_path: {self.user_file}

> 关于用户（主人）的信息

## 基本信息
- **姓名**: [待填写]
- **称呼**: [待填写，如"老板"、"主人"等]

## 偏好
- **编程语言**: [待填写]
- **代码风格**: [待填写，如 tab/空格]
- **沟通方式**: [待填写]

## 已知信息
- **项目**: [待填写]
- **工作**: [待填写]

## 备注
- [待填写]
"""

    def _get_soul_template(self) -> str:
        """获取 SOUL.md 模板"""
        return f"""# SOUL.md

> file_path: {self.soul_file}

> Agent 的性格和沟通风格

## 性格
- [待填写，如：活泼/沉稳/幽默]

## 沟通风格
- [待填写，如：简洁明了/详细解释]

## 习惯
- [待填写]

## 备注
- [待填写]
"""

    def _get_memory_template(self) -> str:
        """获取 MEMORY.md 模板"""
        return f"""# MEMORY.md

> file_path: {self.memory_file}

> 长期记忆 - 重要的决策、偏好和持久的事实

## 重要信息
- [待填写]

## 决策记录
- [待填写]

## 学习笔记
- [待填写]

## 备注
- [待填写]
"""

    def get_agent_memory(self) -> str:
        """获取 AGENT.md 内容"""
        if self.agent_file.exists():
            return self.agent_file.read_text(encoding="utf-8")
        return ""

    def get_user_memory(self) -> str:
        """获取 USER.md 内容"""
        if self.user_file.exists():
            return self.user_file.read_text(encoding="utf-8")
        return ""

    def get_soul_memory(self) -> str:
        """获取 SOUL.md 内容"""
        if self.soul_file.exists():
            return self.soul_file.read_text(encoding="utf-8")
        return ""

    def get_longterm_memory(self) -> str:
        """获取 MEMORY.md 内容"""
        if self.memory_file.exists():
            return self.memory_file.read_text(encoding="utf-8")
        return ""

    def get_daily_memory(self, date: Optional[str] = None) -> str:
        """
        获取每日记忆

        Args:
            date: 日期字符串，格式 YYYY-MM-DD，默认为今天
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        daily_file = self.daily_dir / f"{date}.md"
        if daily_file.exists():
            return daily_file.read_text(encoding="utf-8")
        return ""

    def preload(self, include_daily: bool = True, include_longterm: bool = True) -> dict:
        """
        预加载所有记忆文件

        Args:
            include_daily: 是否包含每日记忆
            include_longterm: 是否包含长期记忆

        Returns:
            包含所有记忆内容的字典
        """
        self._ensure_memory_dir()

        memories = {
            "AGENT": self.get_agent_memory(),
            "USER": self.get_user_memory(),
            "SOUL": self.get_soul_memory(),
        }

        if include_longterm:
            memories["MEMORY"] = self.get_longterm_memory()

        if include_daily:
            # 加载今天和昨天的每日记忆
            today = datetime.now()
            memories["daily_today"] = self.get_daily_memory()
            yesterday = today.replace(day=today.day - 1) if today.day > 1 else today.replace(
                month=today.month - 1, day=28
            )
            # 简单处理：只获取今天的
            memories["daily"] = self.get_daily_memory()

        return memories

    def format_for_context(self, include_daily: bool = True, include_longterm: bool = True) -> str:
        """
        格式化记忆为上下文字符串

        Args:
            include_daily: 是否包含每日记忆
            include_longterm: 是否包含长期记忆

        Returns:
            格式化的记忆字符串
        """
        memories = self.preload(include_daily=include_daily, include_longterm=include_longterm)

        parts = []

        if memories.get("SOUL"):
            parts.append(f"## SOUL\n{memories['SOUL']}")

        if memories.get("AGENT"):
            parts.append(f"## AGENT\n{memories['AGENT']}")

        if memories.get("USER"):
            parts.append(f"## USER\n{memories['USER']}")

        if memories.get("MEMORY") and include_longterm:
            parts.append(f"## MEMORY\n{memories['MEMORY']}")

        if memories.get("daily") and include_daily:
            parts.append(f"## Daily Notes\n{memories['daily']}")

        return "\n\n".join(parts)

    def append_daily_note(self, note: str, date: Optional[str] = None):
        """
        追加每日笔记

        Args:
            note: 要追加的笔记内容
            date: 日期字符串，格式 YYYY-MM-DD，默认为今天
        """
        self._ensure_memory_dir()

        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        daily_file = self.daily_dir / f"{date}.md"

        # 如果文件不存在，创建新文件
        if not daily_file.exists():
            content = f"# {date}\n\n## Notes\n\n"
        else:
            content = daily_file.read_text(encoding="utf-8")
            # 检查是否需要添加新的章节
            if "## Notes\n" not in content and "## Notes\n\n" not in content:
                content += "\n## Notes\n"

        # 添加时间戳
        timestamp = datetime.now().strftime("%H:%M")
        content += f"- {timestamp}: {note}\n"

        daily_file.write_text(content, encoding="utf-8")

    def append_longterm_memory(self, content: str, category: Optional[str] = None):
        """
        追加长期记忆到 MEMORY.md

        Args:
            content: 要追加的记忆内容
            category: 可选的分类（如 "decisions", "preferences", "facts"）
        """
        self._ensure_memory_dir()

        if not self.memory_file.exists():
            mem_content = "# MEMORY.md\n\n> 长期记忆 - 重要的决策、偏好和持久的事实\n\n"
        else:
            mem_content = self.memory_file.read_text(encoding="utf-8")

        # 添加时间戳
        date = datetime.now().strftime("%Y-%m-%d")

        # 构建新的记忆条目
        new_entry = f"\n### {date}"
        if category:
            new_entry += f" ({category})"
        new_entry += f"\n\n{content}\n"

        # 检查是否有更新记录部分
        if "## 更新记录" in mem_content or "## Update" in mem_content:
            # 插入到更新记录之前
            match = re.search(r"(##\s+更新记录|##\s+Update)", mem_content)
            if match:
                pos = match.start()
                mem_content = mem_content[:pos] + new_entry + "\n" + mem_content[pos:]
            else:
                mem_content += new_entry
        else:
            mem_content += new_entry

        self.memory_file.write_text(mem_content, encoding="utf-8")

    def update_memory_file(self, file_name: str, new_content: str, append: bool = False):
        """
        更新指定的记忆文件

        Args:
            file_name: 文件名（AGENT.md, USER.md, SOUL.md, MEMORY.md）
            new_content: 新的内容
            append: 是否追加模式
        """
        self._ensure_memory_dir()

        file_map = {
            "AGENT.md": self.agent_file,
            "USER.md": self.user_file,
            "SOUL.md": self.soul_file,
            "MEMORY.md": self.memory_file,
        }

        file_path = file_map.get(file_name)
        if file_path is None:
            raise ValueError(f"未知的记忆文件: {file_name}")

        if append:
            existing = ""
            if file_path.exists():
                existing = file_path.read_text(encoding="utf-8")
            new_content = existing + "\n" + new_content

        file_path.write_text(new_content, encoding="utf-8")

    def search_memory(self, query: str, search_longterm: bool = True) -> list:
        """
        简单的关键词搜索记忆

        Args:
            query: 搜索关键词
            search_longterm: 是否搜索长期记忆

        Returns:
            匹配结果列表
        """
        results = []
        query_lower = query.lower()

        # 搜索每日记忆
        if self.daily_dir.exists():
            for daily_file in self.daily_dir.glob("*.md"):
                content = daily_file.read_text(encoding="utf-8")
                if query_lower in content.lower():
                    results.append({
                        "file": str(daily_file.relative_to(self.memory_dir)),
                        "type": "daily",
                        "content": self._extract_snippet(content, query),
                    })

        # 搜索长期记忆
        if search_longterm:
            if self.memory_file.exists():
                content = self.memory_file.read_text(encoding="utf-8")
                if query_lower in content.lower():
                    results.append({
                        "file": "MEMORY.md",
                        "type": "longterm",
                        "content": self._extract_snippet(content, query),
                    })

            # 搜索其他记忆文件
            for file_path in [self.agent_file, self.user_file, self.soul_file]:
                if file_path.exists():
                    content = file_path.read_text(encoding="utf-8")
                    if query_lower in content.lower():
                        results.append({
                            "file": file_path.name,
                            "type": file_path.stem.lower(),
                            "content": self._extract_snippet(content, query),
                        })

        return results

    def _extract_snippet(self, content: str, query: str, context_chars: int = 100) -> str:
        """提取包含查询词的片段"""
        query_lower = query.lower()
        content_lower = content.lower()
        pos = content_lower.find(query_lower)

        if pos == -1:
            return content[:200] + "..." if len(content) > 200 else content

        start = max(0, pos - context_chars)
        end = min(len(content), pos + len(query) + context_chars)

        snippet = content[start:end]
        if start > 0:
            snippet = "..." + snippet
        if end < len(content):
            snippet = snippet + "..."

        return snippet


# 全局实例
_default_memory_manager: Optional[MemoryManager] = None


def get_memory_manager(memory_dir: Optional[str] = None) -> MemoryManager:
    """获取全局记忆管理器实例"""
    global _default_memory_manager
    if _default_memory_manager is None:
        _default_memory_manager = MemoryManager(memory_dir)
    return _default_memory_manager


# 便捷函数
def preload_memory(include_daily: bool = True, include_longterm: bool = True) -> dict:
    """预加载记忆"""
    return get_memory_manager().preload(include_daily, include_longterm)


def format_memory_context(include_daily: bool = True, include_longterm: bool = True) -> str:
    """格式化记忆为上下文"""
    return get_memory_manager().format_for_context(include_daily, include_longterm)


def add_daily_note(note: str, date: Optional[str] = None):
    """添加每日笔记"""
    get_memory_manager().append_daily_note(note, date)


def add_memory(content: str, category: Optional[str] = None):
    """添加长期记忆"""
    get_memory_manager().append_longterm_memory(content, category)


def search_memory(query: str, search_longterm: bool = True) -> list:
    """搜索记忆"""
    return get_memory_manager().search_memory(query, search_longterm)
