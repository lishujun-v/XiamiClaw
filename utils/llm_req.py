"""LLM 请求工具 - 兼容新的 models 模块"""

import requests
import json
import logging
from typing import Optional, Generator, Callable

# 导入新的 models 模块
from models import CustomLLM
from utils.logging_utils import format_trace_message, summarize_for_log

# 创建默认实例，保持向后兼容
_default_llm = None
_logger = logging.getLogger("xiamiclaw.llm_req")


def _last_user_message(messages: list | None) -> str:
    if not messages:
        return ""
    for message in reversed(messages):
        if message.get("role") == "user":
            return str(message.get("content", "") or "")
    return ""


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
    logger=None,
    **kwargs
) -> dict:
    """调用 LLM API (兼容旧接口)

    使用 models.CustomLLM 实现

    Args:
        stream: 是否使用流式返回，None 时使用 config.yaml 中的配置
        stream_callback: 流式回调函数，每收到一个 chunk 就会调用一次
    """
    llm = _get_default_llm()
    active_logger = logger or _logger
    # 如果传了 model 参数，更新实例的 model
    if model:
        llm.model = model

    # 如果未指定 stream，使用 config 中的配置
    if stream is None:
        stream = llm.stream

    active_logger.info(
        "Calling LLM | provider=%s model=%s stream=%s messages=%s tools=%s",
        getattr(llm, "provider", "unknown"),
        getattr(llm, "model", model or ""),
        stream,
        len(messages or []),
        len(tools or []),
    )
    active_logger.info(
        format_trace_message(
            "LLM_REQUEST",
            provider=getattr(llm, "provider", "unknown"),
            model=getattr(llm, "model", model or ""),
            stream=stream,
            message_count=len(messages or []),
            tool_count=len(tools or []),
            latest_user_input=summarize_for_log(_last_user_message(messages)),
        )
    )

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
                logger=active_logger,
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
                active_logger.info(
                    format_trace_message(
                        "LLM_RESPONSE",
                        provider=getattr(llm, "provider", "unknown"),
                        model=getattr(llm, "model", model or ""),
                        response_type="tool_call",
                        tool_calls=len(stream_tool_calls),
                        content_preview=summarize_for_log(content),
                    )
                )
                return {
                    'type': 'tool_call',
                    'content': content,
                    'tool_calls': stream_tool_calls,
                }

            # 兼容兜底：有 tools 且流式没有正文时，补一次非流式请求。
            # 部分供应商在流式模式下不返回正文增量，但非流式可返回完整文本或 tool_calls。
            if tools and not content.strip():
                try:
                    fallback = llm.call(
                        prompt=prompt,
                        messages=messages,
                        tools=tools,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        logger=active_logger,
                        **kwargs
                    )
                    if isinstance(fallback, dict):
                        # tool_calls 或文本内容任一有效都返回兜底结果，避免出现空回复。
                        if fallback.get("tool_calls"):
                            return fallback
                        fallback_content = fallback.get("content", "")
                        if isinstance(fallback_content, str) and fallback_content.strip():
                            return fallback
                except Exception:
                    pass

            active_logger.info(
                format_trace_message(
                    "LLM_RESPONSE",
                    provider=getattr(llm, "provider", "unknown"),
                    model=getattr(llm, "model", model or ""),
                    response_type="text",
                    tool_calls=0,
                    content_preview=summarize_for_log(content),
                )
            )
            return {
                'type': 'text',
                'content': content
            }
        except Exception as e:
            active_logger.exception("Streaming LLM call failed")
            return {'type': 'text', 'content': f"流式调用错误: {str(e)}"}
    else:
        try:
            result = llm.call(
                prompt=prompt,
                messages=messages,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
                logger=active_logger,
                **kwargs
            )
            active_logger.info("LLM call completed | type=%s", result.get("type"))
            active_logger.info(
                format_trace_message(
                    "LLM_RESPONSE",
                    provider=getattr(llm, "provider", "unknown"),
                    model=getattr(llm, "model", model or ""),
                    response_type=result.get("type"),
                    tool_calls=len(result.get("tool_calls") or []),
                    content_preview=summarize_for_log(result.get("content", "")),
                )
            )
            return result
        except Exception as e:
            active_logger.exception("LLM call failed")
            return {'type': 'text', 'content': f"LLM 调用错误: {str(e)}"}


def call_llm_stream(
    prompt: str = None,
    messages: list = None,
    tools: list = None,
    model: str = "",
    temperature: float = 0.7,
    max_tokens: int = 4096,
    logger=None,
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
    active_logger = logger or _logger
    # 如果传了 model 参数，更新实例的 model
    if model:
        llm.model = model

    active_logger.info(
        "Calling LLM stream | provider=%s model=%s messages=%s tools=%s",
        getattr(llm, "provider", "unknown"),
        getattr(llm, "model", model or ""),
        len(messages or []),
        len(tools or []),
    )
    yield from llm.call_stream(
        prompt=prompt,
        messages=messages,
        tools=tools,
        temperature=temperature,
        max_tokens=max_tokens,
        logger=active_logger,
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
