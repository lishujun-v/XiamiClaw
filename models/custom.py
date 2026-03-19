"""自定义 LLM API (原 llm_req.py 的逻辑)"""

import requests
import json
from typing import Optional

from .base import BaseLLM
from utils.config import get_model_config


class CustomLLM(BaseLLM):
    """自定义 LLM API (支持多provider)"""

    def __init__(
        self,
        api_key: str = None,
        base_url: str = None,
        model: str = None,
        session_id: str = None,
        temperature: float = None,
        max_tokens: int = None,
        timeout: int = None,
        provider: str = None,
        **kwargs
    ):
        # 如果没有传入参数，从配置文件读取
        config = get_model_config()

        # 获取当前 provider
        current_provider = provider or config.get('provider', 'custom')

        # 如果指定了新的 provider，使用对应的配置
        if provider and provider != config.get('provider'):
            config = config  # 使用传入的 provider

        api_key = api_key or config.get('api_key', '')
        base_url = base_url or config.get('base_url', '')
        model = model or config.get('model', '')
        session_id = session_id or config.get('session_id', '1-SHARE_TITLE')
        temperature = temperature if temperature is not None else config.get('temperature', 0.7)
        max_tokens = max_tokens or config.get('max_tokens', 4096)
        timeout = timeout or config.get('timeout', 600)

        super().__init__(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            **kwargs
        )
        self.session_id = session_id
        self.provider = current_provider

    def call(
        self,
        prompt: str = None,
        messages: list = None,
        tools: list = None,
        **kwargs
    ) -> dict:
        """调用自定义 LLM API"""

        # 根据 provider 构建不同的请求
        if self.provider == 'deepseek':
            return self._call_deepseek(prompt, messages, tools, **kwargs)
        elif self.provider == 'openai':
            return self._call_openai(prompt, messages, tools, **kwargs)
        else:
            # 默认使用百应 custom 格式
            return self._call_custom(prompt, messages, tools, **kwargs)

    def _call_deepseek(self, prompt, messages, tools, **kwargs):
        """调用 DeepSeek API (标准 OpenAI 兼容格式)"""
        url = f"{self.base_url}/v1/chat/completions"

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        }

        # 构建消息
        if messages is None:
            messages = []

        if prompt and not messages:
            messages = [{'role': 'user', 'content': prompt}]

        # 标准化消息
        normalized_messages = self._normalize_messages(messages)

        # 构建请求数据 (标准 OpenAI 格式)
        data = {
            'model': self.model,
            'messages': normalized_messages,
            'temperature': kwargs.get('temperature', self.temperature),
            'max_tokens': kwargs.get('max_tokens', self.max_tokens),
        }

        if tools is not None:
            data['tools'] = tools

        try:
            response = requests.post(
                url=url,
                headers=headers,
                json=data,
                timeout=self.timeout
            )

            response.raise_for_status()
            result = response.json()

            return self._parse_response(result)

        except Exception as e:
            return {
                'type': 'text',
                'content': f"错误：调用 DeepSeek API 失败 - {str(e)}"
            }

    def _call_openai(self, prompt, messages, tools, **kwargs):
        """调用 OpenAI API"""
        return self._call_deepseek(prompt, messages, tools, **kwargs)

    def _call_custom(self, prompt, messages, tools, **kwargs):
        """调用百应自定义 API"""
        url = f"{self.base_url}/v1/chat/completions"

        headers = {
            'Content-Type': 'application/json',
            'authorization': f'Bearer {self.api_key}',
            'X-Baiying-Session-ID': self.session_id
        }

        # 构建消息
        if messages is None:
            messages = []

        if prompt and not messages:
            messages = [
                {
                    'role': 'user',
                    'content': [
                        {'type': 'text', 'text': prompt}
                    ]
                }
            ]

        # 转换消息格式 (百应格式)
        normalized_messages = []
        for msg in messages:
            role = msg.get('role')
            content = msg.get('content')

            if role == 'tool':
                normalized_messages.append({
                    'role': 'tool',
                    'tool_call_id': msg.get('tool_call_id'),
                    'content': content if content else ''
                })
            elif 'tool_calls' in msg and msg['tool_calls']:
                normalized_messages.append({
                    'role': 'assistant',
                    'content': content if content else None,
                    'tool_calls': msg['tool_calls']
                })
            elif isinstance(content, str):
                normalized_messages.append({
                    'role': role,
                    'content': [
                        {'type': 'text', 'text': content}
                    ]
                })
            elif isinstance(content, list):
                normalized_messages.append(msg)
            else:
                normalized_messages.append(msg)

        # 构建请求数据
        data = {
            'request_id': '1',
            'sessionId': '1',
            'model': self.model,
            'messages': normalized_messages,
            'stream': False,
            'temperature': kwargs.get('temperature', self.temperature),
            'max_tokens': kwargs.get('max_tokens', self.max_tokens),
        }

        if tools is not None:
            data['tools'] = tools

        try:
            response = requests.post(
                url=url,
                headers=headers,
                data=json.dumps(data),
                timeout=self.timeout
            )

            response.raise_for_status()
            result = response.json()
            return self._parse_response(result)

        except Exception as e:
            return {
                'type': 'text',
                'content': f"错误：调用 LLM API 失败 - {str(e)}"
            }

    def _normalize_messages(self, messages):
        """标准化消息格式"""
        normalized = []
        for msg in messages:
            role = msg.get('role')
            content = msg.get('content')

            if role == 'tool':
                normalized.append({
                    'role': 'tool',
                    'tool_call_id': msg.get('tool_call_id'),
                    'content': content if content else ''
                })
            elif 'tool_calls' in msg and msg['tool_calls']:
                normalized.append({
                    'role': 'assistant',
                    'content': content if content else None,
                    'tool_calls': msg['tool_calls']
                })
            elif isinstance(content, list):
                normalized.append(msg)
            else:
                normalized.append({
                    'role': role,
                    'content': content
                })

        return normalized

    def _parse_response(self, result):
        """解析 API 响应"""
        if result.get('choices') and len(result['choices']) > 0:
            message = result['choices'][0]['message']

            content = message.get('content', '')

            if 'tool_calls' in message and message['tool_calls']:
                tool_calls = []
                for tc in message['tool_calls']:
                    func = tc.get('function', {})
                    args = func.get('arguments', {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except:
                            args = {}

                    tool_calls.append({
                        'id': tc.get('id', 'call_unknown'),
                        'type': 'function',
                        'function': {
                            'name': func.get('name', ''),
                            'arguments': args
                        }
                    })

                return {
                    'type': 'tool_call',
                    'content': content,
                    'tool_calls': tool_calls
                }
            else:
                return {
                    'type': 'text',
                    'content': content
                }
        else:
            with open('./workspace/llm_error_response.json', 'w', encoding='utf-8') as f:
                json.dump(result, f)
            return {
                'type': 'text',
                'content': "错误：API 返回结果中没有有效内容"
            }
