---
name: npm
description: "Node.js 包管理：install、run、test、build 等"
emoji: 📦
metadata: {"requires": {"bins": ["npm", "node"]}}
---

# NPM Skill

使用 npm 进行 Node.js 包管理和项目操作。

## 常用命令

### 包管理
```bash
npm install
npm install <package>
npm install --save <package>
npm install --save-dev <package>
npm uninstall <package>
```

### 运行脚本
```bash
npm run
npm run <script>
npm start
npm test
npm run build
npm run dev
```

### 全局操作
```bash
npm -g list
npm list
npm list --depth=0
```

### 项目初始化
```bash
npm init
npm init -y
```

### 发布包
```bash
npm publish
npm version patch
```

## 使用场景

- 用户询问 Node.js/npm 相关操作时使用此 skill
- 安装依赖、运行脚本、项目构建等
