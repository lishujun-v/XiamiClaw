#!/usr/bin/env python3
"""
Agentic Loop 使用示例 - 测试 Git Skill
"""

import sys
sys.path.insert(0, '.')

from src.agentic_loop import AgenticLoop
from src.tool_registry import ToolRegistry
from src.skill_loader import SkillLoader
from utils.llm_req import call_llm


def create_llm_provider():
    def llm_provider(messages, tools=None, **kwargs):
        prompt = '\n'.join([f"{m['role']}: {str(m['content'])[:200]}" for m in messages[-4:]])
        return call_llm(prompt=prompt)
    return llm_provider


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("测试: 使用 Git Skill")
    print("=" * 60)

    tool_registry = ToolRegistry()
    skill_loader = SkillLoader()
    skill_loader.load_all()

    llm_provider = create_llm_provider()

    loop = AgenticLoop(
        llm_provider=llm_provider,
        tool_registry=tool_registry,
        skill_loader=skill_loader,
        max_iterations=2,
    )

    # 测试请求 git 相关操作
    result = loop.run('查看当前 git 状态', show_progress=True)
    print(f"\n最终回复: {result[:300]}...")
