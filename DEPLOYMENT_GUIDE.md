# 部署指南

## 本地开发环境部署

### 后端服务部署

系统后端基于FastAPI框架开发，支持快速本地部署和开发调试。

**环境准备**

首先确保系统已安装Python 3.11或更高版本。创建独立的虚拟环境以避免依赖冲突：

```bash
cd character_llm_framework
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows
```

**依赖安装**

虚拟环境激活后，安装项目所需的Python依赖包：

```bash
pip install -r requirements.txt
```

**服务启动**

使用演示版启动脚本启动后端服务：

```bash
python3 run_demo.py
```

服务启动后将在 `http://localhost:8000` 提供API服务，同时可以通过 `http://localhost:8000/docs` 访问Swagger API文档。

### 前端应用部署

前端应用基于React 18和Vite构建，提供现代化的用户交互界面。

**环境准备**

确保系统已安装Node.js 18或更高版本，以及pnpm包管理器。进入前端项目目录：

```bash
cd frontend/character-llm-frontend
```

**依赖安装**

使用pnpm安装前端依赖：

```bash
pnpm install
```

**开发服务启动**

启动Vite开发服务器：

```bash
pnpm run dev --host
```

前端应用将在 `http://localhost:5173` 启动，支持热重载和快速开发调试。

## 生产环境部署

### 容器化部署

系统支持Docker容器化部署，便于在各种环境中快速部署和扩展。

**后端容器化**

创建后端Dockerfile：

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app/ ./app/
COPY run_demo.py .

EXPOSE 8000
CMD ["python", "run_demo.py"]
```

**前端容器化**

创建前端Dockerfile：

```dockerfile
FROM node:18-alpine

WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN npm install -g pnpm && pnpm install

COPY . .
RUN pnpm run build

FROM nginx:alpine
COPY --from=0 /app/dist /usr/share/nginx/html
EXPOSE 80
```

### 云平台部署

系统架构支持在主流云平台上部署，包括AWS、Azure、Google Cloud等。

**后端API部署**

后端API可以部署到云函数服务（如AWS Lambda、Azure Functions）或容器服务（如AWS ECS、Azure Container Instances）。对于高并发场景，建议使用Kubernetes集群进行水平扩展。

**前端静态资源部署**

前端构建后的静态资源可以部署到CDN服务（如AWS CloudFront、Azure CDN），提供全球加速访问。同时可以配置自定义域名和HTTPS证书。

**数据库部署**

演示版本使用SQLite数据库，生产环境建议升级到PostgreSQL或MySQL等企业级数据库。可以使用云数据库服务（如AWS RDS、Azure Database）获得更好的性能和可靠性。

## 配置管理

### 环境变量配置

系统支持通过环境变量进行配置管理，主要配置项包括：

- `DATABASE_URL`: 数据库连接字符串
- `OPENAI_API_KEY`: OpenAI API密钥（用于真实LLM集成）
- `CORS_ORIGINS`: 允许的跨域请求来源
- `DEBUG`: 调试模式开关

### 配置文件管理

可以创建 `.env` 文件进行本地配置管理：

```env
DATABASE_URL=sqlite:///./character_llm.db
DEBUG=true
CORS_ORIGINS=["http://localhost:3000", "http://localhost:5173"]
```

## 性能优化

### 后端性能优化

后端API采用异步处理架构，支持高并发请求处理。对于生产环境，建议进行以下优化：

**数据库优化**：为常用查询字段添加索引，使用连接池管理数据库连接，定期进行数据库维护和优化。

**缓存策略**：对于频繁访问的角色信息和记忆数据，可以使用Redis等缓存系统减少数据库查询压力。

**负载均衡**：使用Nginx或云负载均衡器分发请求到多个后端实例，提高系统整体吞吐量。

### 前端性能优化

前端应用已采用现代化的构建工具和优化策略：

**代码分割**：Vite自动进行代码分割，按需加载组件和资源，减少初始加载时间。

**资源压缩**：生产构建自动压缩JavaScript、CSS和图片资源，减少传输大小。

**缓存策略**：配置适当的HTTP缓存头，利用浏览器缓存提升用户体验。

## 监控和维护

### 日志管理

系统集成了结构化日志记录，支持不同级别的日志输出。生产环境建议使用ELK Stack或云日志服务进行日志收集和分析。

### 健康检查

系统提供健康检查端点 `/health`，可以集成到负载均衡器和监控系统中，实现自动故障检测和恢复。

### 备份策略

定期备份数据库和配置文件，建议使用自动化备份工具和云存储服务确保数据安全。

## 安全考虑

### API安全

生产环境应该实施API认证和授权机制，限制未授权访问。可以使用JWT令牌或OAuth 2.0进行身份验证。

### 数据安全

敏感数据应该进行加密存储，传输过程中使用HTTPS协议保护数据安全。

### 访问控制

配置防火墙规则，限制不必要的网络访问，定期更新系统和依赖包以修复安全漏洞。

通过以上部署指南，可以在各种环境中成功部署和运行角色化大语言模型知识库管理系统，为用户提供稳定可靠的服务。
