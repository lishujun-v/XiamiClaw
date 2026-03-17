---
name: git
description: "Git 版本控制操作：commit、branch、log、stash 等"
emoji: 📦
metadata: {"requires": {"bins": ["git"]}}
---

# Git Skill

使用 Git 进行版本控制操作。

## 常用命令

### 查看状态
```bash
git status
git status -s
```

### 查看提交历史
```bash
git log --oneline -10
git log --graph --oneline --all
```

### 分支操作
```bash
git branch -a
git branch <branch_name>
git checkout <branch_name>
git switch <branch_name>
```

### 提交操作
```bash
git add <file>
git add .
git commit -m "提交信息"
git commit --amend -m "修改提交信息"
```

### 远程操作
```bash
git remote -v
git fetch
git pull
git push
git push -u origin <branch>
```

### 暂存操作
```bash
git stash
git stash list
git stash pop
git stash drop
```

### 查看差异
```bash
git diff
git diff --staged
git diff <branch1> <branch2>
```

## 使用场景

- 用户询问 Git 相关操作时使用此 skill
- 代码版本管理、分支操作等
