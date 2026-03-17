---
name: notes
description: "笔记管理：创建、查看、搜索笔记"
emoji: 📝
metadata: {"requires": {}}
---

# Notes Skill

简单的笔记管理系统。

## 功能

### 创建笔记
```bash
echo "# 我的笔记内容" >> notes/today.md
```

### 查看笔记列表
```bash
ls -la notes/
ls -la notes/*.md
```

### 搜索笔记
```bash
grep -r "关键词" notes/
grep -l "关键词" notes/*.md
```

## 使用场景

- 用户需要记录或查看笔记时使用此 skill
- 记录会议要点、技术备忘等
