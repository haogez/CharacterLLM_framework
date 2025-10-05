# 角色化大语言模型知识库管理系统 - Docker部署指南

## 🚀 快速部署流程

### 第一步：创建Docker容器（在宿主机执行）

```bash
docker run -idt --name zhouyuhao \
  -p 8083:22 \
  -p 8086:8000 \
  -p 9000:80 \
  --gpus all \
  --shm-size 32G \
  -v /home/zhouyuhao:/zhouyuhao \
  python:3.11-slim
```

### 第二步：进入容器并部署

```bash
# 进入容器
docker exec -it zhouyuhao /bin/bash

# 克隆项目
cd /
git clone https://github.com/haogez/CharacterLLM_framework.git
cd /CharacterLLM_framework

# 安装Python依赖
pip3 install -r requirements.txt

# 配置API密钥
cat > .env << 'EOF'
OPENAI_API_KEY=你的API密钥
OPENAI_BASE_URL=https://api.zhizengzeng.com/v1
EOF

# 启动后端
nohup python3 run_with_env.py > backend.log 2>&1 &
echo $! > backend.pid

# 安装Node.js
apt-get update && apt-get install -y curl
curl -fsSL https://deb.nodesource.com/setup_18.x | bash -
apt-get install -y nodejs

# 构建前端
cd frontend/character-llm-frontend
npm install --legacy-peer-deps
npm run build

# 安装并配置Nginx
apt-get install -y nginx
cd /CharacterLLM_framework
cp nginx.conf /etc/nginx/conf.d/default.conf
rm -f /etc/nginx/sites-enabled/default
mkdir -p /usr/share/nginx/html
cp -r frontend/character-llm-frontend/dist/* /usr/share/nginx/html/
service nginx start
```

### 第三步：访问应用

1. 在VSCode PORTS面板添加端口转发：`8086` 和 `9000`
2. 浏览器访问：
   - 前端：http://localhost:9000
   - API文档：http://localhost:8086/docs

---

## 端口映射

| 容器内 | 宿主机 | 用途 |
|-------|-------|------|
| 8000 | 8086 | 后端API |
| 80 | 9000 | 前端界面 |

---

**部署完成！** 🎉
