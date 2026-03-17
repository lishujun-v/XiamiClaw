---
name: docker
description: "Docker 容器操作：run、build、ps、images 等"
emoji: 🐳
metadata: {"requires": {"bins": ["docker"]}}
---

# Docker Skill

使用 Docker 进行容器操作。

## 常用命令

### 容器操作
```bash
docker ps
docker ps -a
docker run -it <image> /bin/bash
docker start <container_id>
docker stop <container_id>
docker rm <container_id>
docker logs <container_id>
```

### 镜像操作
```bash
docker images
docker pull <image>
docker rmi <image>
docker build -t <name> .
```

### 进入容器
```bash
docker exec -it <container_id> /bin/bash
docker exec -it <container_id> sh
```

### 查看资源
```bash
docker stats
docker inspect <container_id>
docker network ls
docker volume ls
```

### 清理
```bash
docker system prune
docker container prune
docker image prune
```

## 使用场景

- 用户询问 Docker 相关操作时使用此 skill
- 容器管理、镜像构建等
