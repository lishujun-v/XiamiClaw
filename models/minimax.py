"""Minimax LLM API"""

import requests
import json
from typing import Optional

from .base import BaseLLM


class MinimaxLLM(BaseLLM):
    """Minimax API"""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.minimax.chat/v1",
        model: str = "MiniMax-Text-01",
        group_id: str = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        timeout: int = 600,
        **kwargs
    ):
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            **kwargs
        )
        self.group_id = group_id

    def call(
        self,
        prompt: str = None,
        messages: list = None,
        tools: list = None,
        **kwargs
    ) -> dict:
        """调用 Minimax API"""
        url = f"{self.base_url}/text/chatcompletion_v2"

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        }

        if self.group_id:
            headers['Authorization'] = f'Bearer {self.api_key}; {self.group_id}'

        messages = self._build_messages(prompt, messages)

        # 转换消息格式
        normalized_messages = self._normalize_messages(messages)

        data = {
            'model': kwargs.get('model', self.model),
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
                data=json.dumps(data),
                timeout=self.timeout
            )

            response.raise_for_status()
            result = response.json()

            return self._format_response(result)

        except Exception as e:
            return {
                'type': 'text',
                'content': f"错误：调用 Minimax API 失败 - {str(e)}"
            }

    def _normalize_messages(self, messages: list) -> list:
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

    def _format_response(self, response_data: dict) -> dict:
        """格式化响应数据"""
        if response_data.get('choices') and len(response_data['choices']) > 0:
            message = response_data['choices'][0]['message']

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
            return {
                'type': 'text',
                'content': "错误：API 返回结果中没有有效内容"
            }
