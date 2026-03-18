"""自定义 LLM API (原 llm_req.py 的逻辑)"""

import requests
import json
from typing import Optional

from .base import BaseLLM


class CustomLLM(BaseLLM):
    """自定义 LLM API (百应模型)"""

    def __init__(
        self,
        api_key: str = "sk-fc19155e-54de-475e-b259-5ea4ef8294ea_tool",
        base_url: str = "https://llm-model-api-test.baiying.com.cn",
        model: str = "216224dc-465d-48d7-9aa2-2c177d7c2405",  # dp v32
        # model: str = "doubao-seed-2-0-mini-260215",  # seed2.0-mini
        # model: str = "0b43e386-3460-4e06-b631-c7a3df450aaf",  # kimi-k2.5

        session_id: str = "1-SHARE_TITLE",
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
        self.session_id = session_id

    def call(
        self,
        prompt: str = None,
        messages: list = None,
        tools: list = None,
        **kwargs
    ) -> dict:
        """调用自定义 LLM API"""
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

        # 转换消息格式
        normalized_messages = []
        for msg in messages:
            role = msg.get('role')
            content = msg.get('content')

            # 处理 tool 角色消息
            if role == 'tool':
                normalized_messages.append({
                    'role': 'tool',
                    'tool_call_id': msg.get('tool_call_id'),
                    'content': content if content else ''
                })
            # 处理有 tool_calls 的 assistant 消息
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

            # 提取 LLM 返回的内容
            if result.get('choices') and len(result['choices']) > 0:
                message = result['choices'][0]['message']

                # content 可能是字符串或列表
                content = message.get('content', '')
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get('type') == 'text':
                            content = item.get('text', '')
                            break

                # 检查是否有工具调用
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

        except Exception as e:
            return {
                'type': 'text',
                'content': f"错误：调用 LLM API 失败 - {str(e)}"
            }
