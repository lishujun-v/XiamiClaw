---
name: github
description: "使用 gh CLI 与 GitHub 交互：PR、Issue、Repo 等操作"
emoji: 🐙
metadata: {"requires": {"bins": ["gh"]}}
---

# GitHub Skill

使用 GitHub CLI (`gh`) 与 GitHub 进行交互。

## 常用命令

### 查看 PR 列表
```bash
gh pr list --limit 10
```

### 查看 PR 详情
```bash
gh pr view <pr_number>
```

### 查看 Issue 列表
```bash
gh issue list --limit 10
```

### 查看仓库信息
```bash
gh repo view <owner>/<repo>
```

### 创建 Issue
```bash
gh issue create --title "标题" --body "内容"
```

### 查看 Actions
```bash
gh run list --limit 10
```

## 使用场景

- 用户询问 GitHub 相关操作时使用此 skill
- 查询 PR、Issue、Actions 等
- 管理仓库和创建 Issue
