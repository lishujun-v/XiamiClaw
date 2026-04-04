# XiamiClaw

一个基于 Agent 架构的 AI 助手，支持多种大模型接入，可以执行工具调用、Skill 技能等任务。

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/your-repo/XiamiClaw.git
cd XiamiClaw
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

**注意**：macOS 用户推荐安装 `gnureadline` 以获得更好的中文输入体验：

```bash
pip install gnureadline
```

### 3. 配置模型

编辑 `config.yaml` 文件，配置你使用的 LLM：

```yaml
# 选择模型提供商: deepseek / openai / anthropic / custom
model_provider: deepseek

# DeepSeek 配置
deepseek:
  api_key: "sk-你的API密钥"
  base_url: "https://api.deepseek.com"
  model: "deepseek-chat"  # 或 deepseek-coder
  stream: true

# OpenAI 配置
openai:
  api_key: "sk-你的API密钥"
  base_url: "https://api.openai.com/v1"
  model: "gpt-4o"
  stream: true

# Anthropic (Claude) 配置
anthropic:
  api_key: "sk-ant-你的API密钥"
  model: "claude-sonnet-4-20250514"
  stream: true

# 自定义 API (百应) 配置
custom:
  api_key: "你的API密钥"
  base_url: "https://你的API地址"
  model: "模型ID"
  stream: true
```

### 4. 启动命令

**交互模式**（会显示带框线的输入框）：

```bash
python cli.py
```

**单次执行**：

```bash
python cli.py "你好，请介绍一下自己"
```

**查看 System Prompt**：

```bash
python cli.py -s
```

## 多 Agent 模式

XiamiClaw 支持同时创建多个 Agent，每个 Agent 拥有独立的工作目录（Workspace），实现任务的并行处理和隔离。

### Agent 配置

在 `config.yaml` 中配置多个 Agent：

```yaml
agents:
  # 默认 agent（如果不指定使用哪个 agent，则使用这个）
  default: "agent1"

  # Agent 列表，每个 agent 有独立的工作目录
  list:
    - name: "agent1"
      workspace: "./workspace"
      description: "通用任务处理：代码开发、文件操作等"

    - name: "agent2"
      workspace: "./workspace_agent2"
      description: "文档与报告撰写"

    - name: "agent3"
      workspace: "./workspace_agent3"
      description: "测试与调试"
```

### 切换 Agent

在交互模式下，使用 `/agent` 命令切换不同的 Agent：

```
/agent agent2    # 切换到 agent2
/agent list      # 查看所有可用 Agent
/agent current   # 查看当前 Agent
```

### Agent 特性

- **独立 Workspace**：每个 Agent 在自己的工作目录中操作，互不干扰
- **独立会话**：每个 Agent 维护自己的对话历史
- **并行处理**：可以同时运行多个 Agent 处理不同任务
- **灵活配置**：每个 Agent 可以配置不同的描述和职责

## 使用说明

### 交互模式命令

- 输入消息开始对话
- `/exit` / `/quit` / `/q` - 退出程序
- `/skills` - 查看可用技能
- `/tools` - 查看可用工具
- `/clear` - 清屏
- `/prompt` - 显示当前 System Prompt
- `/new` - 创建新 session（清除历史对话）
- `/agent` - Agent 管理命令（见上文）

### 命令行参数

```bash
# 交互模式
python cli.py -i

# 单次执行
python cli.py "你的消息"

# 显示 System Prompt
python cli.py -s

# 禁用危险工具执行前确认
python cli.py -i --no-confirm

# 指定最大迭代次数
python cli.py "你的消息" --max-iterations 5

# 查看帮助
python cli.py -h
```

**参数说明：**

| 参数 | 说明 |
|------|------|
| `-i`, `--interactive` | 交互模式 |
| `-s`, `--show-prompt` | 显示 System Prompt |
| `--no-confirm` | 禁用危险工具（exec/write/edit）执行前确认 |
| `--max-iterations` | 最大迭代次数（默认 10） |

### 配置文件说明

`config.yaml` 中可配置的选项：

```yaml
# Agent 配置
agent:
  max_iterations: 100   # 最大循环次数
  verbose: true         # 是否显示详细日志

# CLI 配置
cli:
  welcome_message: "OpenClaw Agent"  # 欢迎信息
  input_width: 0       # 输入框宽度，0 表示自动
```

## 项目结构

```
XiamiClaw/
├── cli.py              # 命令行入口
├── config.yaml         # 配置文件
├── models/             # LLM 模型封装
├── src/                # 核心代码
├── tools/              # 工具集
├── skills/             # 技能集
├── utils/              # 工具函数
├── workspace/          # 默认 Agent 工作目录
├── workspace_agent2/   # Agent2 工作目录
└── workspace_agent3/   # Agent3 工作目录
```

## 日志

- 每个 Agent 会在自己的 Workspace 下自动创建 `logs/` 目录
- 日志文件默认命名为 `agent名_YYYY-MM-DD.log`
- 当天单个日志文件达到 `5MB` 后，会自动切换到 `agent名_YYYY-MM-DD_01.log`、`_02.log` ...
- 关键日志已覆盖：CLI 启动、Agent 初始化、LLM 请求、工具调用、Skill 加载、Session 持久化、运行异常

## 环境要求

- Python 3.10+
- 支持的 LLM API：DeepSeek、OpenAI、Anthropic、百应等兼容 OpenAI API 格式的模型
