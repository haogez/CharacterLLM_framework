# 角色化大语言模型知识库管理系统 - Docker部署指南

本文档提供了使用Docker和Docker Compose在VSCode远程服务器上部署角色化大语言模型知识库管理系统的详细步骤。该部署方案已针对智增增API代理服务进行了优化和测试。

## 1. 核心技术栈

| 组件 | 技术 | 说明 |
| --- | --- | --- |
| **前端** | React (Vite) | 提供用户交互界面，用于创建和管理角色，并进行智能对话。 |
| **后端** | FastAPI | 提供RESTful API，处理角色生成、记忆管理和对话生成等核心逻辑。 |
| **代理** | Nginx | 作为反向代理，将前端请求和后端API请求路由到正确的服务。 |
| **容器化** | Docker | 将前后端应用打包成独立的容器，实现环境隔离和快速部署。 |
| **LLM集成** | 智增增API | 通过智增增平台代理访问大语言模型，用于角色和对话生成。 |

## 2. 部署步骤

### 2.1. 克隆代码仓库

首先，将修复后的代码仓库克隆到您的VSCode远程服务器：

```bash
git clone https://github.com/haogez/CharacterLLM_framework.git
cd CharacterLLM_framework
```

### 2.2. 配置环境变量

在项目根目录创建一个名为`.env`的文件，用于存放您的API密钥和配置。请将`your_zhizengzeng_api_key_here`替换为您自己的智增增API密钥。

```bash
# .env

# 智增增平台API配置
OPENAI_API_KEY=sk-zk2fbc13c9dacbd9d1c577991155e25fa2568e256f5de463
OPENAI_BASE_URL=https://api.zhizengzeng.com/v1

# 应用配置
CORS_ORIGINS=["http://localhost:5173","http://localhost:80"]
```

### 2.3. 构建并启动Docker容器

在项目根目录运行以下命令，使用Docker Compose构建并启动所有服务。`-d`参数表示在后台运行。

```bash
docker-compose up --build -d
```

此命令将执行以下操作：

- **构建后端镜像**：基于`Dockerfile.backend`，安装Python依赖并启动FastAPI服务。
- **构建前端镜像**：基于`frontend/character-llm-frontend/Dockerfile.frontend`，使用Vite构建React应用，并将其部署到Nginx服务器。
- **启动服务**：同时启动后端API服务和前端Nginx服务。

### 2.4. 访问应用

服务启动后，您可以通过以下地址访问应用：

- **前端界面**：[http://localhost:5173](http://localhost:5173)
- **后端API文档**：[http://localhost:8000/docs](http://localhost:8000/docs)

## 3. 关键配置文件解析

### 3.1. `docker-compose.yml`

该文件定义了`backend`和`frontend`两个服务，并配置了它们之间的依赖关系和端口映射。

```yaml
version: '3'

services:
  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    ports:
      - "8000:8000"
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - OPENAI_BASE_URL=${OPENAI_BASE_URL}
    volumes:
      - ./:/app

  frontend:
    build:
      context: ./frontend/character-llm-frontend
      dockerfile: Dockerfile.frontend
    ports:
      - "5173:80"
    depends_on:
      - backend
```

### 3.2. `nginx.conf`

Nginx配置将所有`/api/v1/`开头的请求代理到后端服务（`http://backend:8000`），并将其他请求指向前端静态文件。

```nginx
server {
    listen 80;
    server_name localhost;

    location / {
        root /usr/share/nginx/html;
        index index.html index.htm;
        try_files $uri $uri/ /index.html;
    }

    location /api/v1/ {
        proxy_pass http://backend:8000/api/v1/;
        # ... 其他代理配置
    }
}
```

### 3.3. `vite.config.js`

前端Vite配置中，`base: '/'`确保了资源能被正确加载，而`server.proxy`配置则用于开发环境下的API代理。

```javascript
export default defineConfig({
  // ...
  base: '/',
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      }
    }
  }
})
```

## 4. 故障排除

- **前端无法加载**：请检查`docker-compose logs frontend`，确认Nginx是否正常启动，以及前端文件是否已成功复制到`/usr/share/nginx/html`。
- **API调用失败**：请检查`docker-compose logs backend`，确认后端服务是否正常运行，以及`.env`文件中的API密钥和URL是否正确。
- **模型不支持错误**：请确保您的智增增API支持`gpt-4.1-mini`模型。如果不支持，您需要修改`app/core/llm/openai_client.py`中的默认模型配置。

---

*文档由Manus AI生成，最后更新于2025年10月5日。*
