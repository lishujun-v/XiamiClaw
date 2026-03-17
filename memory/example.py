#!/usr/bin/env python3
"""
Memory Module Example / 示例

展示如何使用 memory 模块进行记忆管理和上下文预加载
"""

from memory import (
    MemoryManager,
    preload_memory,
    format_memory_context,
    add_daily_note,
    add_memory,
    get_memory_manager,
)


def example_basic_usage():
    """基础使用示例"""
    print("=" * 50)
    print("1. 基础使用示例")
    print("=" * 50)

    # 获取 memory 管理器
    manager = get_memory_manager()

    # 预加载所有记忆
    memories = manager.preload()
    print("\n预加载的记忆文件:")
    for key, value in memories.items():
        if value:
            print(f"  - {key}: {len(value)} chars")
        else:
            print(f"  - {key}: (empty)")

    # 格式化记忆为上下文
    context = manager.format_for_context()
    print(f"\n格式化的上下文长度: {len(context)} chars")


def example_add_notes():
    """添加笔记示例"""
    print("\n" + "=" * 50)
    print("2. 添加笔记示例")
    print("=" * 50)

    # 添加每日笔记
    add_daily_note("开始测试 memory 模块")
    add_daily_note("完成基础功能开发")

    # 添加长期记忆
    add_memory(
        "测试了 memory 模块的基础功能，包括预加载、添加笔记和搜索",
        category="development"
    )


def example_search():
    """搜索示例"""
    print("\n" + "=" * 50)
    print("3. 搜索示例")
    print("=" * 50)

    manager = get_memory_manager()

    # 搜索记忆
    results = manager.search_memory("memory")
    print(f"\n搜索 'memory' 的结果: {len(results)} 个")

    for result in results:
        print(f"\n  文件: {result['file']}")
        print(f"  类型: {result['type']}")
        print(f"  片段: {result['content'][:100]}...")


def example_context_for_agent():
    """为 Agent 准备上下文示例"""
    print("\n" + "=" * 50)
    print("4. 为 Agent 准备上下文")
    print("=" * 50)

    # 获取完整上下文
    context = format_memory_context(
        include_daily=True,
        include_longterm=True
    )

    print(f"\n上下文内容 ({len(context)} chars):")
    print("-" * 40)
    print(context[:500] if len(context) > 500 else context)
    if len(context) > 500:
        print("...")


def example_custom_dir():
    """自定义目录示例"""
    print("\n" + "=" * 50)
    print("5. 使用自定义目录")
    print("=" * 50)

    # 使用自定义 memory 目录
    custom_manager = MemoryManager("/path/to/custom/memory")
    print(f"自定义目录: {custom_manager.memory_dir}")


if __name__ == "__main__":
    example_basic_usage()
    example_add_notes()
    example_search()
    example_context_for_agent()
    example_custom_dir()

    print("\n" + "=" * 50)
    print("示例完成!")
    print("=" * 50)
