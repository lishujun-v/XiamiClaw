import requests
import json
from typing import Optional


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
    """调用 LLM API"""
    url = "https://llm-model-api-test.baiying.com.cn/v1/chat/completions"

    headers = {
        'Content-Type': 'application/json',
        'authorization': 'Bearer sk-fc19155e-54de-475e-b259-5ea4ef8294ea_tool',
        'X-Baiying-Session-ID': '1-SHARE_TITLE'
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

        # 处理 tool 角色消息 - 必须包含 tool_call_id
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
        'model': model,
        'messages': normalized_messages,
        'stream': stream,
        'temperature': temperature,
        'max_tokens': max_tokens,
    }

    if tools is not None:
        data['tools'] = tools

    timeout_seconds = 600

    try:
        response = requests.post(
            url=url,
            headers=headers,
            data=json.dumps(data),
            timeout=timeout_seconds
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
            return {
                'type': 'text',
                'content': "错误：API 返回结果中没有有效内容"
            }

    except Exception as e:
        return {
            'type': 'text',
            'content': f"错误：调用 LLM API 失败 - {str(e)}"
        }


def call_llm_simple(prompt: str) -> str:
    """简单的 LLM 调用，返回纯文本"""
    result = call_llm(prompt=prompt)
    return result.get('content', '')


if __name__ == "__main__":
    result = call_llm("你好")
    print(result)
