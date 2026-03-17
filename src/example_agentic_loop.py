#!/usr/bin/env python3
"""
Agentic Loop 使用示例
"""

import sys
sys.path.insert(0, '.')

from src.agentic_loop import AgenticLoop
from src.tool_registry import ToolRegistry
from src.skill_loader import SkillLoader
from utils.llm_req import call_llm


def create_llm_provider():
    """创建 LLM 提供函数"""
    def llm_provider(messages, tools=None, **kwargs):
        # 直接传递 messages 和 tools 给 call_llm
        return call_llm(messages=messages, tools=tools)
    return llm_provider


if __name__ == "__main__":
    # 先测试打印 system prompt
    # query = "帮我调用exec工具查看下当前所在目录"
    # query = "请帮我写一段 Python 代码，功能是获取当前系统时间并打印出来。"
    # query = "编辑一下当前目录下的test.txt文件，写个笑话进去"
    query = "帮我写一个py文件，执行它 打印一个心出来给我看"
    print("\n" + "=" * 10)
    print(f"测试: {query}")
    print("=" * 20)

    tool_registry = ToolRegistry()
    skill_loader = SkillLoader()
    skill_loader.load_all()

    llm_provider = create_llm_provider()

    loop = AgenticLoop(
        llm_provider=llm_provider,
        tool_registry=tool_registry,
        skill_loader=skill_loader,
        max_iterations=10,
    )

    # 打印 system prompt
    # print("\n=== System Prompt ===")
    # print(loop._build_system_prompt()[:3000])
    # print("\n... (truncated)")

    result = loop.run(query, show_progress=True)
    print(f"\n最终回复: {result}...")
