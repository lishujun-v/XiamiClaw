"""自定义 LLM API (原 llm_req.py 的逻辑)"""

import requests
import json
import logging
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
        # 默认跟随请求超时，避免某些 provider 在流式结束后不主动断开连接时长时间挂起。
        self.read_timeout = (
            read_timeout
            if read_timeout is not None
            else config.get('read_timeout', timeout)
        )
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
        self.logger = logging.getLogger("xiamiclaw.models.custom")

    def _build_chat_completions_url(self) -> str:
        """构建 OpenAI 兼容接口的 chat completions URL。"""
        base = self.base_url.rstrip('/')
        if base.endswith('/v1'):
            return f"{base}/chat/completions"
        return f"{base}/v1/chat/completions"

    def _build_minimax_chat_url(self) -> str:
        """构建 Minimax chatcompletion_v2 URL，兼容 base_url 是否包含 /v1。"""
        base = self.base_url.rstrip('/')
        if base.endswith('/text/chatcompletion_v2'):
            return base
        if base.endswith('/v1'):
            return f"{base}/text/chatcompletion_v2"
        return f"{base}/v1/text/chatcompletion_v2"

    def call(
        self,
        prompt: str = None,
        messages: list = None,
        tools: list = None,
        **kwargs
    ) -> dict:
        """调用自定义 LLM API"""

        # 根据 provider 构建不同的请求
        if self.provider in ('deepseek', 'openai', 'qwen', 'kimi'):
            return self._call_deepseek(prompt, messages, tools, **kwargs)
        elif self.provider == 'minimax':
            return self._call_minimax(prompt, messages, tools, **kwargs)
        else:
            # 默认使用百应 custom 格式
            return self._call_custom(prompt, messages, tools, **kwargs)

    def _call_deepseek(self, prompt, messages, tools, **kwargs):
        """调用 DeepSeek API (标准 OpenAI 兼容格式)"""
        logger = kwargs.get("logger") or self.logger
        url = self._build_chat_completions_url()

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
            logger.info("Requesting OpenAI-compatible LLM | provider=%s url=%s tools=%s", self.provider, url, len(tools or []))
            response = requests.post(
                url=url,
                headers=headers,
                json=data,
                timeout=self._timeout_tuple
            )

            response.raise_for_status()
            result = response.json()

            return self._parse_response(result, workspace=kwargs.get("workspace"), logger=logger)

        except Exception as e:
            logger.exception("OpenAI-compatible LLM request failed")
            return {
                'type': 'text',
                'content': f"错误：调用 DeepSeek API 失败 - {str(e)}"
            }

    def _call_openai(self, prompt, messages, tools, **kwargs):
        """调用 OpenAI API"""
        return self._call_deepseek(prompt, messages, tools, **kwargs)

    def _call_minimax(self, prompt, messages, tools, **kwargs):
        """调用 Minimax API"""
        logger = kwargs.get("logger") or self.logger
        # 从 extra_kwargs 获取 group_id
        group_id = self.extra_kwargs.get('group_id')

        url = self._build_minimax_chat_url()

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
            logger.info("Requesting Minimax LLM | url=%s tools=%s", url, len(tools or []))
            response = requests.post(
                url=url,
                headers=headers,
                json=data,
                timeout=self._timeout_tuple
            )

            response.raise_for_status()
            result = response.json()

            return self._parse_response(result, workspace=kwargs.get("workspace"), logger=logger)

        except Exception as e:
            logger.exception("Minimax LLM request failed")
            return {
                'type': 'text',
                'content': f"错误：调用 Minimax API 失败 - {str(e)}"
            }

    def _call_custom(self, prompt, messages, tools, **kwargs):
        """调用百应自定义 API"""
        logger = kwargs.get("logger") or self.logger
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
            logger.info("Requesting custom LLM | url=%s tools=%s", url, len(tools or []))
            response = requests.post(
                url=url,
                headers=headers,
                data=json.dumps(data),
                timeout=self._timeout_tuple
            )

            response.raise_for_status()
            result = response.json()
            return self._parse_response(result, workspace=kwargs.get("workspace"), logger=logger)

        except Exception as e:
            logger.exception("Custom LLM request failed")
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
            normalized_role = role
            normalized_content = content

            # minimax/custom 对 system 角色兼容性较差，尤其是在多轮和 tool
            # 往返后插入新的 system 消息时，服务端会直接报 invalid role。
            # 将其降级为 user，并显式保留系统语义，兼容动态注入的 skill/context。
            if role == 'system' and self.provider in ('minimax', 'custom'):
                normalized_role = 'user'
                if isinstance(content, str):
                    normalized_content = f"[SYSTEM]\n{content}"
                elif isinstance(content, list):
                    normalized_content = []
                    for entry in content:
                        if isinstance(entry, dict) and entry.get('type') == 'text':
                            normalized_content.append({
                                **entry,
                                'text': f"[SYSTEM]\n{entry.get('text', '')}"
                            })
                        else:
                            normalized_content.append(entry)

            if normalized_role == 'tool':
                normalized.append({
                    'role': 'tool',
                    'tool_call_id': msg.get('tool_call_id'),
                    'content': normalized_content if normalized_content else ''
                })
            elif 'tool_calls' in msg and msg['tool_calls']:
                normalized.append({
                    'role': 'assistant',
                    'content': normalized_content if normalized_content else None,
                    'tool_calls': msg['tool_calls']
                })
            elif isinstance(normalized_content, list):
                normalized.append({
                    **msg,
                    'role': normalized_role,
                    'content': normalized_content,
                })
            else:
                normalized.append({
                    'role': normalized_role,
                    'content': normalized_content
                })

        return normalized

    def _parse_response(self, result, workspace: str = None, logger=None):
        """解析 API 响应"""
        logger = logger or self.logger
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
            dump_path = None
            try:
                base_dir = workspace or "./workspace"
                dump_path = f"{base_dir}/llm_error_response.json"
                with open(dump_path, 'w', encoding='utf-8') as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
            except Exception:
                logger.exception("Failed to persist raw LLM error response")
            logger.error("LLM response missing choices. Dumped raw response to %s", dump_path or "(unavailable)")

            # 透传供应商错误，避免仅提示“没有有效内容”
            provider_error = None
            if isinstance(result, dict):
                if isinstance(result.get("error"), dict):
                    provider_error = result.get("error", {}).get("message")
                if not provider_error:
                    provider_error = result.get("message")
                if not provider_error:
                    provider_error = result.get("msg")
                if not provider_error:
                    code = result.get("errorCode") or result.get("code")
                    if code is not None:
                        provider_error = f"code={code}"

            if provider_error:
                return {
                    'type': 'text',
                    'content': f"错误：API 返回异常 - {provider_error}"
                }

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
                current['name'] = self._merge_stream_fragment(
                    current.get('name', ''),
                    name_part
                )

            args_part = func.get('arguments')
            if isinstance(args_part, str):
                current['arguments'] = self._merge_stream_fragment(
                    current.get('arguments', ''),
                    args_part
                )
            elif isinstance(args_part, dict):
                # 少数供应商可能直接给对象，统一成 JSON 字符串再解析
                if not current['arguments']:
                    current['arguments'] = json.dumps(args_part, ensure_ascii=False)

    def _merge_stream_fragment(self, current: str, incoming: str) -> str:
        """合并流式字符串片段，兼容增量片段和累计快照两种供应商行为。"""
        if not incoming:
            return current or ''

        current = current or ''
        if not current:
            return incoming

        if incoming == current:
            return current

        # 某些供应商会重复返回“截至当前为止”的完整内容，而非纯增量片段。
        if incoming.startswith(current):
            return incoming

        if current.endswith(incoming):
            return current

        max_overlap = min(len(current), len(incoming))
        for overlap in range(max_overlap, 0, -1):
            if current.endswith(incoming[:overlap]):
                return current + incoming[overlap:]

        return current + incoming

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
                                else:
                                    # 兼容少数供应商：choices[].message.tool_calls。
                                    # 部分供应商会在同一个 chunk 中同时返回 delta/tool_calls
                                    # 和 message/tool_calls，两者通常是同一份数据；此处只在
                                    # delta 缺失时再读取 message，避免把工具名和参数重复拼接。
                                    message_tool_calls = (choice.get('message', {}) or {}).get('tool_calls')
                                    if message_tool_calls:
                                        self._merge_stream_tool_calls(stream_calls, message_tool_calls)
                            # 某些 provider 不发送 data: [DONE]，而是只在最后一个 chunk 里给 finish_reason。
                            # 如果这里不提前结束，iter_lines() 会一直等到服务端主动断开连接或读超时。
                            finish_reason = choice.get('finish_reason')
                            if finish_reason is not None:
                                break
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
        if self.provider in ('deepseek', 'openai', 'qwen', 'kimi'):
            yield from self._call_deepseek_stream(prompt, messages, tools, **kwargs)
        elif self.provider == 'minimax':
            yield from self._call_minimax_stream(prompt, messages, tools, **kwargs)
        else:
            # 默认使用百应 custom 格式
            yield from self._call_custom_stream(prompt, messages, tools, **kwargs)

    def _call_deepseek_stream(self, prompt, messages, tools, **kwargs):
        """流式调用 DeepSeek/OpenAI API"""
        logger = kwargs.get("logger") or self.logger
        url = self._build_chat_completions_url()

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
            logger.info("Requesting OpenAI-compatible stream | provider=%s url=%s tools=%s", self.provider, url, len(tools or []))
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
            logger.exception("OpenAI-compatible streaming request failed")
            self._last_stream_tool_calls = []
            yield f"错误：调用 DeepSeek API 失败 - {str(e)}"

    def _call_minimax_stream(self, prompt, messages, tools, **kwargs):
        """流式调用 Minimax API"""
        logger = kwargs.get("logger") or self.logger
        group_id = self.extra_kwargs.get('group_id')

        url = self._build_minimax_chat_url()

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
            logger.info("Requesting Minimax stream | url=%s tools=%s", url, len(tools or []))
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
            logger.exception("Minimax streaming request failed")
            self._last_stream_tool_calls = []
            yield f"错误：调用 Minimax API 失败 - {str(e)}"

    def _call_custom_stream(self, prompt, messages, tools, **kwargs):
        """流式调用百应自定义 API"""
        logger = kwargs.get("logger") or self.logger
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
            logger.info("Requesting custom stream | url=%s tools=%s", url, len(tools or []))
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
            logger.exception("Custom streaming request failed")
            self._last_stream_tool_calls = []
            yield f"错误：调用 LLM API 失败 - {str(e)}"
