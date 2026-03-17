# Agentic Loop 模块

实现 ReAct 模式的 Agent 循环，参考 OpenClaw 的架构设计。

## 功能特性

1. **渐进式 Skill 加载**: 按需加载 skill 内容，减少 token 消耗
2. **ReAct 模式执行**: Think → Action → Observe → Reflect 循环
3. **友好的交互提示**:
   - 启动提示
   - 迭代进度
   - 工具调用提示（带参数显示）
   - 工具执行结果
   - 思考中提示
   - 最终响应
4. **循环检测**: 防止无限循环调用
5. **Memory 集成**: 自动记录任务到 memory

## 目录结构

```
src/
├── agentic_loop.py       # 核心模块
├── example_agentic_loop.py  # 使用示例
├── agent.py              # Master Agent
├── tool_registry.py     # 工具注册表
├── skill_loader.py      # Skill 加载器
└── executor.py          # 执行器

memory/
├── AGENT.md             # Agent 记忆
├── USER.md              # 用户记忆
├── SOUL.md              # 灵魂记忆
├── MEMORY.md            # 长期记忆
└── daily/               # 每日笔记
```

## 使用方法

### 1. 基础使用

```python
from src.agentic_loop import AgenticLoop
from src.tool_registry import ToolRegistry
from src.skill_loader import SkillLoader

# 创建组件
tool_registry = ToolRegistry()
skill_loader = SkillLoader()
skill_loader.load_all()

# 创建 Agentic Loop
loop = AgenticLoop(
    llm_provider=your_llm_provider,  # 你的 LLM 提供函数
    tool_registry=tool_registry,
    skill_loader=skill_loader,
    max_iterations=10,
)

# 运行
result = loop.run("请帮我读取文件", show_progress=True)
```

### 2. LLM 提供函数格式

```python
def my_llm_provider(messages, tools=None, **kwargs):
    """
    messages: 消息历史列表
    tools: 可用工具列表
    返回格式:
    {
        "type": "text",
        "content": "文本响应",
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "tool_name",
                    "arguments": {"param1": "value1"}
                }
            }
        ]
    }
    """
    # 调用你的 LLM API
    return response
```

### 3. 便捷函数

```python
from src.agentic_loop import run_agentic_loop

result = run_agentic_loop(
    user_message="请帮我完成任务",
    llm_provider=my_llm_provider,
    tool_registry=tool_registry,
    show_progress=True,
)
```

## 交互提示示例

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Agentic Loop 启动
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

▶ 迭代 1/10 | 工具调用: 0 | 耗时: 0.0s

🤔 思考中...

⚡ 正在调用工具: read
{
  "path": "src/agent.py"
}

✓ 工具执行成功

...

▶ 迭代 2/10 | 工具调用: 1 | 耗时: 0.1s

🤔 思考中...

========================================
  最终响应
========================================

我已经完成了您的请求...
```

## 循环检测

当检测到重复的工具调用时：

- **警告**: 达到 `loop_warning_threshold` 次时显示警告
- **阻止**: 达到 `loop_max_threshold` 次时阻止执行

```
⚠️  循环检测警告:
工具 `read` 已被连续调用 3 次，可能陷入循环。

🛑 循环被阻止:
工具 `read` 达到最大调用次数限制，停止执行。
```

## 配置选项

```python
loop = AgenticLoop(
    llm_provider=...,
    tool_registry=...,
    skill_loader=...,

    max_iterations=10,              # 最大迭代次数
    max_tool_calls_per_iteration=5, # 每次迭代最大工具调用数
    enable_loop_detection=True,      # 启用循环检测
    loop_warning_threshold=3,       # 循环警告阈值
    loop_max_threshold=5,          # 循环最大阈值
)
```

## 与 Memory 集成

Agentic Loop 自动使用 memory 模块：

- 预加载记忆到系统提示
- 自动记录每日工作笔记
- 记录长期记忆（如用户偏好）

```python
# 查看 memory 上下文
from memory import format_memory_context
context = format_memory_context()
```

## 参考

- [OpenClaw Memory 设计](https://github.com/openclaw/openclaw)
- [ReAct 模式](https://arxiv.org/abs/2210.03629)
