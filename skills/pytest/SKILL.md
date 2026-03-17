---
name: pytest
description: "Python 测试框架：运行测试、查看覆盖率"
emoji: 🧪
metadata: {"requires": {"bins": ["pytest", "python"]}}
---

# Pytest Skill

使用 pytest 运行 Python 测试。

## 常用命令

### 运行测试
```bash
pytest
pytest tests/
pytest test_file.py
pytest test_file.py::test_function
```

### 详细输出
```bash
pytest -v
pytest -vv
pytest -s
```

### 运行特定测试
```bash
pytest -k "test_name"
pytest -k "test_name and not slow"
```

### 标记测试
```bash
pytest -m "slow"
pytest -m "not slow"
```

### 查看覆盖率
```bash
pytest --cov=src
pytest --cov=src --cov-report=html
```

### 失败时停止
```bash
pytest -x
pytest -x -v
```

## 使用场景

- 用户询问 Python 单元测试时使用此 skill
- 运行测试用例、检查测试覆盖率
