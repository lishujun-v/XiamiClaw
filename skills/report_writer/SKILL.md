---
name: report_writer
description: "使用 AI 撰写 Markdown 格式的专业报告"
emoji: 📝
metadata: {"requires": {"python": true, "files": ["scripts/report_writer.py"]}}
---

# 报告撰写 Skill

使用 AI 根据给定的任务目标撰写 Markdown 格式的专业报告。

## 调用脚本

```bash
python skills/report_writer/scripts/report_writer.py -t "任务目标" -c "上下文信息" --timeout 300
```

### 参数说明

| 参数 | 说明 | 示例 |
|------|------|------|
| `--target` / `-t` | 任务目标，要撰写什么内容的报告 | "做一个AI发展趋势相关的报告" |
| `--context` / `-c` | 上下文/背景信息（可选） | "重点关注2024-2025年的技术突破" |
| `--timeout` | LLM 调用超时时间（秒），默认 300 | 300 |

## 使用示例

### 基础用法

```bash
python skills/report_writer/scripts/report_writer.py -t "做一个AI发展趋势相关的报告"
```

### 带上下文

```bash
python skills/report_writer/scripts/report_writer.py -t "撰写技术调研报告" -c "重点关注大语言模型的最新进展"
```

### 输出说明

该命令会直接打印生成的 Markdown 报告内容，可作为其他大模型的上下文参考。

## 报告结构

生成的报告包含以下部分：
- 标题
- 引言
- 主体分析（多个章节）
- 结论
