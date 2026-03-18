"""LLM 请求工具 - 兼容新的 models 模块"""

import requests
import json
from typing import Optional

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
    model: str = "216224dc-465d-48d7-9aa2-2c177d7c2405",
    temperature: float = 0.7,
    max_tokens: int = 4096,
    stream: bool = False,
    **kwargs
) -> dict:
    """调用 LLM API (兼容旧接口)

    使用 models.CustomLLM 实现
    """
    llm = _get_default_llm()
    # 如果传了 model 参数，更新实例的 model
    if model != "216224dc-465d-48d7-9aa2-2c177d7c2405":
        llm.model = model

    return llm.call(
        prompt=prompt,
        messages=messages,
        tools=tools,
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs
    )


def call_llm_simple(prompt: str) -> str:
    """简单的 LLM 调用，返回纯文本"""
    result = call_llm(prompt=prompt)
    return result.get('content', '')


if __name__ == "__main__":
    result = call_llm("你好")
    print(result)
