"""LLM 请求工具 - 兼容新的 models 模块"""

import requests
import json
from typing import Optional, Generator, Callable

# 导入新的 models 模块
from models import CustomLLM

# 创建默认实例，保持向后兼容
_default_llm = None


def _get_default_llm():
    """获取默认 LLM 实例"""
    global _default_llm
    if _default_llm is None:
        _default_llm = CustomLLM()
    return _default_llm


def call_llm(
    prompt: str = None,
    messages: list = None,
    tools: list = None,
    model: str = "",
    temperature: float = 0.7,
    max_tokens: int = 4096,
    stream: bool = None,
    stream_callback: Callable[[str], None] = None,
    **kwargs
) -> dict:
    """调用 LLM API (兼容旧接口)

    使用 models.CustomLLM 实现

    Args:
        stream: 是否使用流式返回，None 时使用 config.yaml 中的配置
        stream_callback: 流式回调函数，每收到一个 chunk 就会调用一次
    """
    llm = _get_default_llm()
    # 如果传了 model 参数，更新实例的 model
    if model:
        llm.model = model

    # 如果未指定 stream，使用 config 中的配置
    if stream is None:
        stream = llm.stream

    if stream:
        # 流式调用
        try:
            chunks = []
            for chunk in llm.call_stream(
                prompt=prompt,
                messages=messages,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            ):
                chunks.append(chunk)
                # 如果有回调，调用它
                if stream_callback:
                    stream_callback(chunk)
            content = ''.join(chunks)

            # 优先使用流式解析得到的结构化 tool_calls（若供应商支持）
            stream_tool_calls = []
            if tools and hasattr(llm, "get_last_stream_tool_calls"):
                try:
                    stream_tool_calls = llm.get_last_stream_tool_calls() or []
                except Exception:
                    stream_tool_calls = []

            if stream_tool_calls:
                return {
                    'type': 'tool_call',
                    'content': content,
                    'tool_calls': stream_tool_calls,
                }

            # 兼容兜底：有 tools 且流式没有正文时，补一次非流式拿 tool_calls
            if tools and not content.strip():
                try:
                    fallback = llm.call(
                        prompt=prompt,
                        messages=messages,
                        tools=tools,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        **kwargs
                    )
                    if isinstance(fallback, dict) and fallback.get("tool_calls"):
                        return fallback
                except Exception:
                    pass

            return {
                'type': 'text',
                'content': content
            }
        except Exception as e:
            return {'type': 'text', 'content': f"流式调用错误: {str(e)}"}
    else:
        try:
            return llm.call(
                prompt=prompt,
                messages=messages,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
        except Exception as e:
            return {'type': 'text', 'content': f"LLM 调用错误: {str(e)}"}


def call_llm_stream(
    prompt: str = None,
    messages: list = None,
    tools: list = None,
    model: str = "",
    temperature: float = 0.7,
    max_tokens: int = 4096,
    **kwargs
) -> Generator[str, None, None]:
    """流式调用 LLM API，yield 返回文本片段

    Args:
        prompt: 提示词
        messages: 消息列表
        tools: 工具列表
        model: 模型名称
        temperature: 温度参数
        max_tokens: 最大 token 数

    Yields:
        str: 文本片段
    """
    llm = _get_default_llm()
    # 如果传了 model 参数，更新实例的 model
    if model:
        llm.model = model

    yield from llm.call_stream(
        prompt=prompt,
        messages=messages,
        tools=tools,
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs
    )


def call_llm_simple(prompt: str, stream: bool = None) -> str:
    """简单的 LLM 调用，返回纯文本

    Args:
        prompt: 提示词
        stream: 是否使用流式返回，None 时使用 config.yaml 中的配置
    """
    result = call_llm(prompt=prompt, stream=stream)
    return result.get('content', '')


def call_llm_simple_stream(prompt: str) -> str:
    """简单的 LLM 流式调用，返回合并后的纯文本"""
    return ''.join(call_llm_stream(prompt=prompt))


if __name__ == "__main__":
    result = call_llm("你好")
    print(result)
