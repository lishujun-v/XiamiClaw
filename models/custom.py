"""自定义 LLM API (原 llm_req.py 的逻辑)"""

import requests
import json
from typing import Optional, Generator

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
        read_timeout: int = None,
        provider: str = None,
        group_id: str = None,
        stream: bool = None,
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
        group_id = group_id or config.get('group_id', '')
        temperature = temperature if temperature is not None else config.get('temperature', 0.7)
        max_tokens = max_tokens or config.get('max_tokens', 4096)
        timeout = timeout or config.get('timeout', 600)
        # 读取超时，默认 1800秒(30分钟)，生成大内容时需要更长
        self.read_timeout = read_timeout or config.get('read_timeout', 1800)
        # 流式返回配置，默认 False
        self.stream = stream if stream is not None else config.get('stream', False)

        # 将 group_id 放入 kwargs 传给 BaseLLM
        if group_id:
            kwargs['group_id'] = group_id

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
        self._timeout_tuple = (timeout, self.read_timeout)
        self._last_stream_tool_calls = []

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
        elif self.provider == 'minimax':
            return self._call_minimax(prompt, messages, tools, **kwargs)
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
                timeout=self._timeout_tuple
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

    def _call_minimax(self, prompt, messages, tools, **kwargs):
        """调用 Minimax API"""
        # 从 extra_kwargs 获取 group_id
        group_id = self.extra_kwargs.get('group_id')

        url = f"{self.base_url}/text/chatcompletion_v2"

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        }

        if group_id:
            headers['Authorization'] = f'Bearer {self.api_key}; {group_id}'

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
                timeout=self._timeout_tuple
            )

            response.raise_for_status()
            result = response.json()

            return self._parse_response(result)

        except Exception as e:
            return {
                'type': 'text',
                'content': f"错误：调用 Minimax API 失败 - {str(e)}"
            }

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
                timeout=self._timeout_tuple
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
            # normalized_role = role
            # normalized_content = content

            # if role == 'system' and self.provider in ('minimax', 'custom'):
            #     normalized_role = 'user'
            #     if isinstance(content, str):
            #         normalized_content = f"[SYSTEM]\n{content}"
            #     elif isinstance(content, list):
            #         normalized_content = [
            #             {'type': 'text', 'text': f"[SYSTEM]\n{entry.get('text', '')}"}
            #             if isinstance(entry, dict) else entry
            #             for entry in content
            #         ]
            #     else:
            #         normalized_content = content
            # else:
            #     normalized_role = role
            #     normalized_content = content

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
            with open(f'./workspace/llm_error_response.json', 'w', encoding='utf-8') as f:
                json.dump(result, f)
            return {
                'type': 'text',
                'content': "错误：API 返回结果中没有有效内容"
            }

    def _merge_stream_tool_calls(self, stream_calls: dict, deltas: list):
        """合并流式返回中的 tool_calls 增量片段。"""
        for tc in deltas or []:
            if not isinstance(tc, dict):
                continue

            index = tc.get('index')
            if index is None:
                index = len(stream_calls)

            if index not in stream_calls:
                stream_calls[index] = {
                    'id': '',
                    'name': '',
                    'arguments': '',
                }

            current = stream_calls[index]
            if tc.get('id'):
                current['id'] = tc['id']

            func = tc.get('function', {}) or {}
            name_part = func.get('name')
            if isinstance(name_part, str):
                current['name'] += name_part

            args_part = func.get('arguments')
            if isinstance(args_part, str):
                current['arguments'] += args_part
            elif isinstance(args_part, dict):
                # 少数供应商可能直接给对象，统一成 JSON 字符串再解析
                if not current['arguments']:
                    current['arguments'] = json.dumps(args_part, ensure_ascii=False)

    def _finalize_stream_tool_calls(self, stream_calls: dict) -> list:
        """将流式累计的 tool_calls 状态转换为 OpenAI 兼容格式。"""
        result = []
        for i, index in enumerate(sorted(stream_calls.keys())):
            item = stream_calls[index]
            args_raw = (item.get('arguments') or '').strip()
            arguments = {}
            if args_raw:
                try:
                    arguments = json.loads(args_raw)
                except Exception:
                    arguments = args_raw

            result.append({
                'id': item.get('id') or f'call_{i}',
                'type': 'function',
                'function': {
                    'name': item.get('name', ''),
                    'arguments': arguments
                }
            })
        return result

    def get_last_stream_tool_calls(self) -> list:
        """获取最近一次流式调用解析出的 tool_calls。"""
        return self._last_stream_tool_calls or []

    def _parse_sse_stream(
        self,
        response: requests.Response,
        collect_tool_calls: bool = False
    ) -> Generator[str, None, None]:
        """解析 SSE 流式响应，并在需要时收集 tool_calls。"""
        stream_calls = {} if collect_tool_calls else None

        for line in response.iter_lines():
            if line:
                line = line.decode('utf-8')
                # 处理 data:{"choices":... 格式（data: 后无空格）或 data: {...} 格式（有空格）
                if line.startswith('data:'):
                    data = line[5:]  # 去掉 'data:' 前缀
                    if data.startswith(' '):
                        data = data[1:]  # 去掉可能的空格
                    if data == '[DONE]' or data.strip() == '[DONE]':
                        break
                    try:
                        json_data = json.loads(data)
                        # 处理 chat.completion.chunk 格式
                        if 'choices' in json_data and len(json_data['choices']) > 0:
                            choice = json_data['choices'][0]
                            delta = choice.get('delta', {}) or {}
                            if 'content' in delta and delta['content']:
                                yield delta['content']
                            if collect_tool_calls:
                                # 常见流式格式：choices[].delta.tool_calls
                                delta_tool_calls = delta.get('tool_calls')
                                if delta_tool_calls:
                                    self._merge_stream_tool_calls(stream_calls, delta_tool_calls)

                                # 兼容少数供应商：choices[].message.tool_calls
                                message_tool_calls = (choice.get('message', {}) or {}).get('tool_calls')
                                if message_tool_calls:
                                    self._merge_stream_tool_calls(stream_calls, message_tool_calls)
                    except json.JSONDecodeError:
                        continue

        if collect_tool_calls:
            self._last_stream_tool_calls = self._finalize_stream_tool_calls(stream_calls)
        else:
            self._last_stream_tool_calls = []

    def call_stream(
        self,
        prompt: str = None,
        messages: list = None,
        tools: list = None,
        **kwargs
    ) -> Generator[str, None, None]:
        """流式调用 LLM API，yield 返回文本片段"""
        self._last_stream_tool_calls = []

        # 根据 provider 构建不同的请求
        if self.provider == 'deepseek':
            yield from self._call_deepseek_stream(prompt, messages, tools, **kwargs)
        elif self.provider == 'openai':
            yield from self._call_deepseek_stream(prompt, messages, tools, **kwargs)
        elif self.provider == 'minimax':
            yield from self._call_minimax_stream(prompt, messages, tools, **kwargs)
        else:
            # 默认使用百应 custom 格式
            yield from self._call_custom_stream(prompt, messages, tools, **kwargs)

    def _call_deepseek_stream(self, prompt, messages, tools, **kwargs):
        """流式调用 DeepSeek/OpenAI API"""
        url = f"{self.base_url}/v1/chat/completions"

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        }

        if messages is None:
            messages = []

        if prompt and not messages:
            messages = [{'role': 'user', 'content': prompt}]

        normalized_messages = self._normalize_messages(messages)

        data = {
            'model': self.model,
            'messages': normalized_messages,
            'temperature': kwargs.get('temperature', self.temperature),
            'max_tokens': kwargs.get('max_tokens', self.max_tokens),
            'stream': True,
        }

        if tools is not None:
            data['tools'] = tools

        try:
            response = requests.post(
                url=url,
                headers=headers,
                json=data,
                timeout=self._timeout_tuple,
                stream=True
            )

            response.raise_for_status()

            for chunk in self._parse_sse_stream(response, collect_tool_calls=bool(tools)):
                yield chunk

        except Exception as e:
            self._last_stream_tool_calls = []
            yield f"错误：调用 DeepSeek API 失败 - {str(e)}"

    def _call_minimax_stream(self, prompt, messages, tools, **kwargs):
        """流式调用 Minimax API"""
        group_id = self.extra_kwargs.get('group_id')

        url = f"{self.base_url}/text/chatcompletion_v2"

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        }

        if group_id:
            headers['Authorization'] = f'Bearer {self.api_key}; {group_id}'

        if messages is None:
            messages = []

        if prompt and not messages:
            messages = [{'role': 'user', 'content': prompt}]

        normalized_messages = self._normalize_messages(messages)

        data = {
            'model': self.model,
            'messages': normalized_messages,
            'temperature': kwargs.get('temperature', self.temperature),
            'max_tokens': kwargs.get('max_tokens', self.max_tokens),
            'stream': True,
        }

        if tools is not None:
            data['tools'] = tools

        try:
            response = requests.post(
                url=url,
                headers=headers,
                json=data,
                timeout=self._timeout_tuple,
                stream=True
            )

            response.raise_for_status()

            for chunk in self._parse_sse_stream(response, collect_tool_calls=bool(tools)):
                yield chunk

        except Exception as e:
            self._last_stream_tool_calls = []
            yield f"错误：调用 Minimax API 失败 - {str(e)}"

    def _call_custom_stream(self, prompt, messages, tools, **kwargs):
        """流式调用百应自定义 API"""
        url = f"{self.base_url}/v1/chat/completions"

        headers = {
            'Content-Type': 'application/json',
            'authorization': f'Bearer {self.api_key}',
            'X-Baiying-Session-ID': self.session_id
        }

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

        data = {
            'request_id': '1',
            'sessionId': '1',
            'model': self.model,
            'messages': normalized_messages,
            'stream': True,
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
                timeout=self._timeout_tuple,
                stream=True
            )

            response.raise_for_status()

            for chunk in self._parse_sse_stream(response, collect_tool_calls=bool(tools)):
                yield chunk

        except Exception as e:
            self._last_stream_tool_calls = []
            yield f"错误：调用 LLM API 失败 - {str(e)}"
