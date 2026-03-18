"""Base LLM 抽象类"""

from abc import ABC, abstractmethod
from typing import Optional, Any


class BaseLLM(ABC):
    """所有 LLM 模型的基类"""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        timeout: int = 600,
        **kwargs
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.extra_kwargs = kwargs

    @abstractmethod
    def call(
        self,
        prompt: str = None,
        messages: list = None,
        tools: list = None,
        **kwargs
    ) -> dict:
        """调用 LLM API

        Returns:
            dict: 包含 'type' ('text' 或 'tool_call') 和 'content' 的字典
        """
        pass

    def call_simple(self, prompt: str) -> str:
        """简单的 LLM 调用，返回纯文本"""
        result = self.call(prompt=prompt)
        return result.get('content', '')

    def _build_messages(self, prompt: str = None, messages: list = None) -> list:
        """构建消息列表"""
        if messages is None:
            messages = []

        if prompt and not messages:
            messages = [
                {
                    'role': 'user',
                    'content': prompt
                }
            ]
        return messages

    def _format_response(self, response_data: dict) -> dict:
        """格式化响应数据"""
        # 子类可以重写此方法
        return response_data
