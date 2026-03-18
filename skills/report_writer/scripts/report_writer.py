#!/usr/bin/env python3
"""
报告撰写脚本 (Report Writer Script)

用于根据给定的任务目标生成 Markdown 格式的报告。

用法:
    python report_writer.py <task_description> [context]

示例:
    python report_writer.py "做一个AI发展趋势相关的报告"
    python report_writer.py "撰写技术调研报告" "重点关注大语言模型的最新进展"
"""

import sys
import os
import argparse

# 添加项目根目录到路径，以便导入 models 模块
# 脚本路径: skills/report_writer/scripts/report_writer.py
# 项目根目录: XiamiClaw/
script_dir = os.path.dirname(os.path.abspath(__file__))
# skills/report_writer/scripts -> skills/report_writer -> skills -> 项目根目录
project_root = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
sys.path.insert(0, project_root)

from models.custom import CustomLLM


def build_prompt(task_description: str, context: str = "") -> str:
    """构建发送给 LLM 的提示词"""
    base_prompt = f"""请完成以下任务：{task_description}

要求：
1. 使用 Markdown 格式输出
2. 内容全面、结构清晰
3. 包含引言、主体分析和结论
4. 使用适当的标题层级 (# ## ###)
5. 内容专业、详实

"""

    if context:
        base_prompt += f"\n背景信息/上下文：{context}\n"

    base_prompt += "\n请开始撰写："

    return base_prompt


def call_llm(prompt: str) -> str:
    """调用 LLM 生成报告内容"""
    llm = CustomLLM()
    result = llm.call(prompt=prompt)

    if result.get('type') == 'text':
        return result.get('content', '')
    elif result.get('type') == 'tool_call':
        return result.get('content', '')
    else:
        return str(result)


def main():
    parser = argparse.ArgumentParser(
        description="报告撰写脚本 - 根据任务目标生成 Markdown 报告",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python report_writer.py "做一个AI发展趋势相关的报告"
    python report_writer.py "撰写技术调研报告" "重点关注大语言模型的最新进展"
        """
    )

    parser.add_argument(
        'task_description',
        nargs='?',
        help='任务目标，如"做一个AI发展趋势相关的报告"'
    )

    parser.add_argument(
        'context',
        nargs='?',
        help='上下文/背景信息'
    )

    parser.add_argument(
        '-t', '--target',
        dest='target',
        help='任务目标 (与位置参数效果相同)'
    )

    parser.add_argument(
        '-c', '--context',
        dest='context_opt',
        help='上下文/背景信息'
    )

    args = parser.parse_args()

    # 合并参数：位置参数和选项参数
    task_description = args.target or args.task_description
    context = args.context_opt or args.context

    if not task_description:
        print("错误：请提供任务目标")
        print("用法: python report_writer.py <task_description> [context]")
        sys.exit(1)

    # 构建 prompt 并调用 LLM
    prompt = build_prompt(task_description, context)
    report_content = call_llm(prompt)

    # 直接打印报告内容，作为大模型的上下文参考
    print(report_content)


if __name__ == "__main__":
    main()
