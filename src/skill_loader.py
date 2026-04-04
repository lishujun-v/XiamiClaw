"""
技能加载器 - 加载和管理 Skills
"""

import os
import re
import subprocess
import logging
from typing import Optional
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SkillMetadata:
    """Skill 元数据"""
    name: str
    description: str
    emoji: str = ""
    requires_bins: list = field(default_factory=list)


@dataclass
class SkillEntry:
    """Skill 条目"""
    skill: SkillMetadata
    file_path: str
    content: str = ""


class SkillLoader:
    """Skill 加载器"""

    def __init__(self, skills_dir: str = "workspace/skills", logger=None):
        self.skills_dir = skills_dir
        self._skills: list[SkillEntry] = []
        self._loaded: set[str] = set()  # 已加载的 skill 内容
        self.logger = logger or logging.getLogger("xiamiclaw.skill_loader")

    def load_all(self) -> list[SkillEntry]:
        """加载所有 skills"""
        self._skills = []

        if not os.path.exists(self.skills_dir):
            self.logger.info("Skills directory does not exist: %s", self.skills_dir)
            return self._skills

        for item in os.listdir(self.skills_dir):
            skill_path = os.path.join(self.skills_dir, item)
            if os.path.isdir(skill_path):
                skill_file = os.path.join(skill_path, "SKILL.md")
                if os.path.exists(skill_file):
                    skill = self._parse_skill_file(skill_file)
                    if skill:
                        self._skills.append(skill)

        self.logger.info("Loaded %s skills from %s", len(self._skills), self.skills_dir)
        return self._skills

    def _parse_skill_file(self, file_path: str) -> Optional[SkillEntry]:
        """解析 SKILL.md 文件"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 解析 YAML frontmatter
            metadata = {}
            if content.startswith('---'):
                end_idx = content.find('---', 3)
                if end_idx > 0:
                    frontmatter = content[3:end_idx].strip()
                    content = content[end_idx + 3:].strip()

                    for line in frontmatter.split('\n'):
                        if ':' in line:
                            key, value = line.split(':', 1)
                            metadata[key.strip()] = value.strip().strip('"')

            # 解析 metadata JSON
            requires_bins = []
            if 'metadata' in metadata:
                import json
                try:
                    meta = json.loads(metadata['metadata'])
                    requires_bins = meta.get('requires', {}).get('bins', [])
                except:
                    pass

            name = metadata.get('name', os.path.basename(os.path.dirname(file_path)))
            description = metadata.get('description', '')

            # 提取 emoji
            emoji_match = re.search(r'emoji:\s*(\S)', metadata.get('emoji', ''))
            emoji = metadata.get('emoji', '') or ''

            return SkillEntry(
                skill=SkillMetadata(
                    name=name,
                    description=description,
                    emoji=emoji,
                    requires_bins=requires_bins
                ),
                file_path=file_path,
                content=content
            )

        except Exception as e:
            self.logger.exception("Failed to parse skill file: %s", file_path)
            return None

    def filter_by_bins(self, available_bins: list[str]) -> list[SkillEntry]:
        """根据可用工具过滤 skills"""
        filtered = []
        for skill in self._skills:
            required = skill.skill.requires_bins
            if not required:
                filtered.append(skill)
            elif all(bin in available_bins for bin in required):
                filtered.append(skill)
        return filtered

    def get_skill_content(self, skill_name: str) -> Optional[str]:
        """获取 skill 内容（渐进式加载）"""
        for skill in self._skills:
            if skill.skill.name == skill_name:
                key = f"{self.skills_dir}/{skill_name}"
                if key not in self._loaded:
                    self._loaded.add(key)
                    self.logger.info("Skill content loaded into context: %s", skill_name)
                return skill.content
        return None

    def build_snapshot(self, skills: list[SkillEntry]) -> dict:
        """构建 skills 快照"""
        return {
            "skills": [
                {
                    "name": s.skill.name,
                    "description": s.skill.description,
                    "emoji": s.skill.emoji,
                    "location": s.file_path
                }
                for s in skills
            ]
        }

    def format_skills_prompt(self, snapshot: dict) -> str:
        """格式化 skills prompt"""
        lines = ["<available_skills>"]
        for s in snapshot["skills"]:
            lines.append(f"  <skill>")
            lines.append(f"    <name>{s['name']}</name>")
            lines.append(f"    <description>{s['description']}</description>")
            lines.append(f"    <emoji>{s['emoji']}</emoji>")
            lines.append(f"    <location>{s['location']}</location>")
            lines.append(f"  </skill>")
        lines.append("</available_skills>")
        return "\n".join(lines)

    def get_all_skills(self) -> list[SkillEntry]:
        """获取所有已加载的 skills"""
        return self._skills
