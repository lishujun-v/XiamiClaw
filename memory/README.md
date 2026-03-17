# Memory Module

参考 OpenClaw 的 memory 实现，为 Python Agent 提供的记忆管理模块。

## 目录结构

```
memory/
├── AGENT.md        # Agent 记忆 - 角色、能力、行为模式
├── USER.md         # 用户记忆 - 偏好、沟通习惯
├── SOUL.md         # 灵魂记忆 - 核心价值观、使命
├── MEMORY.md       # 长期记忆 - 重要决策、偏好、持久事实
├── daily/          # 每日日志
│   └── YYYY-MM-DD.md
└── __init__.py     # 记忆管理模块
```

## 使用方法

### 1. 初始化和预加载

```python
from memory import (
    MemoryManager,
    preload_memory,
    format_memory_context,
)

# 方式1: 使用全局管理器
manager = get_memory_manager()

# 方式2: 使用自定义目录
manager = MemoryManager("/path/to/custom/memory")

# 预加载所有记忆
memories = manager.preload()

# 格式化为上下文字符串（用于 Agent 上下文）
context = format_memory_context(include_daily=True, include_longterm=True)
```

### 2. 添加记忆

```python
from memory import add_daily_note, add_memory

# 添加每日笔记
add_daily_note("今天完成了某个任务")

# 添加长期记忆（带分类）
add_memory(
    "用户偏好使用中文交流",
    category="preferences"
)
```

### 3. 搜索记忆

```python
from memory import get_memory_manager

manager = get_memory_manager()

# 简单关键词搜索
results = manager.search_memory("偏好")
for result in results:
    print(f"文件: {result['file']}")
    print(f"内容: {result['content']}")
```

### 4. 在 Agent 中使用

```python
from memory import format_memory_context

# 在启动 Agent 前获取记忆上下文
context = format_memory_context()

# 将上下文注入 Agent 的 system prompt
system_prompt = f"""
你是一个智能助手。

## 记忆
{context}

请根据上述记忆来帮助用户。
"""
```

## OpenClaw Memory 设计原则

参考 OpenClaw 的 memory 设计：

1. **记忆文件即真理**: Markdown 文件是记忆的来源，模型只"记住"写入磁盘的内容
2. **分层记忆**:
   - `memory/YYYY-MM-DD.md` - 每日日志（只追加），会话开始时读取今天和昨天
   - `MEMORY.md` - 精选的长期记忆
3. **何时写记忆**:
   - 决策、偏好和持久事实 → `MEMORY.md`
   - 日常笔记和运行上下文 → `memory/YYYY-MM-DD.md`
   - 如果用户说"记住这个"，就写下来
4. **自动记忆刷新**: 会话接近自动压缩时，触发静默的记忆刷新

## Memory 文件说明

| 文件 | 用途 | 加载时机 |
|------|------|----------|
| `AGENT.md` | Agent 的身份、能力、行为模式 | 始终加载 |
| `USER.md` | 用户偏好、沟通习惯 | 始终加载 |
| `SOUL.md` | Agent 的核心价值观、使命 | 始终加载 |
| `MEMORY.md` | 长期记忆（重要决策、偏好） | 按需加载 |
| `daily/YYYY-MM-DD.md` | 每日工作笔记 | 加载今天和昨天 |

## API 参考

### MemoryManager 类

```python
class MemoryManager:
    def __init__(self, memory_dir: str = None)
    def preload(include_daily=True, include_longterm=True) -> dict
    def format_for_context(include_daily=True, include_longterm=True) -> str
    def get_agent_memory() -> str
    def get_user_memory() -> str
    def get_soul_memory() -> str
    def get_longterm_memory() -> str
    def get_daily_memory(date: str = None) -> str
    def append_daily_note(note: str, date: str = None)
    def append_longterm_memory(content: str, category: str = None)
    def update_memory_file(file_name: str, new_content: str, append: bool = False)
    def search_memory(query: str, search_longterm: bool = True) -> list
```

### 便捷函数

- `get_memory_manager(memory_dir: str = None) -> MemoryManager`
- `preload_memory(include_daily: bool = True, include_longterm: bool = True) -> dict`
- `format_memory_context(include_daily: bool = True, include_longterm: bool = True) -> str`
- `add_daily_note(note: str, date: str = None)`
- `add_memory(content: str, category: str = None)`
