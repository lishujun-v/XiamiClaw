---
name: search
description: "代码搜索：在项目中搜索文件、函数、文本内容"
emoji: 🔍
metadata: {"requires": {"bins": ["grep", "find", "rg"]}}
---

# Search Skill

在项目中进行代码搜索。

## 常用命令

### 文本搜索
```bash
grep "关键词" -r .
rg "关键词"
find . -name "*.py" | xargs grep "关键词"
```

### 文件搜索
```bash
find . -name "*.py"
find . -name "*.json"
find . -name "*test*"
```

### 搜索文件内容 (rg 推荐)
```bash
rg "函数名" --type py
rg "class " --type js
rg -l "关键词"  # 只显示文件名
rg -c "关键词"  # 显示行数
```

### 搜索文件名
```bash
find . -name "*.md"
find . -name "*config*"
```

### 排除目录搜索
```bash
rg "关键词" --glob "!node_modules/*"
rg "关键词" --glob "!*.test.js"
```

## 使用场景

- 用户需要在项目中搜索代码时使用此 skill
- 查找函数定义、搜索关键词等
