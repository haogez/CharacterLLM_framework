# Docker部署指南

本文档提供了如何使用Docker部署角色化大语言模型知识库管理系统的详细说明。

## 前提条件

- 安装Docker和Docker Compose
- 获取OpenAI API密钥（或智增增平台API密钥）

## 快速部署

### 1. 创建环境变量文件

在项目根目录创建`.env`文件：

```bash
# 使用智增增平台API
OPENAI_API_KEY=your_zhizengzeng_api_key_here
OPENAI_BASE_URL=https://api.zhizengzeng.com/v1
```

### 2. 使用Docker Compose启动服务

```bash
docker-compose up -d
```

这将启动后端API服务和前端Web应用。

### 3. 访问应用

- 前端界面：http://localhost:5173
- API文档：http://localhost:8000/docs

## 在VSCode中使用Docker部署

如果您在VSCode中使用Docker容器开发，可以按照以下步骤操作：

### 1. 在Docker容器中构建前端

```bash
cd /CharacterLLM_framework/frontend/character-llm-frontend
npm install --legacy-peer-deps
npm run build
```

### 2. 使用Nginx提供前端服务

在Docker容器中安装Nginx：

```bash
apt-get update
apt-get install -y nginx
```

复制Nginx配置：

```bash
cp /CharacterLLM_framework/nginx.conf /etc/nginx/conf.d/default.conf
```

复制构建产物到Nginx目录：

```bash
mkdir -p /usr/share/nginx/html
cp -r /CharacterLLM_framework/frontend/character-llm-frontend/dist/* /usr/share/nginx/html/
```

启动Nginx：

```bash
service nginx start
```

### 3. 启动后端服务

在另一个终端中：

```bash
cd /CharacterLLM_framework
python run_with_env.py
```

### 4. 设置端口转发

在VSCode中，设置端口转发：
- 前端：80 -> 5173
- 后端：8000 -> 8000

然后在本地浏览器中访问：
- http://localhost:5173

## 故障排除

### 前端无法连接后端

如果前端无法连接后端API，请检查：

1. Nginx配置是否正确
2. 后端服务是否正常运行
3. 端口转发是否设置正确

### API调用失败

如果API调用失败，请检查：

1. 环境变量是否正确设置
2. 智增增平台API密钥是否有效
3. 后端日志中是否有错误信息

## 自定义配置

### 修改端口

如果需要修改端口，请更新以下文件：

1. `docker-compose.yml`中的端口映射
2. `nginx.conf`中的监听端口

### 修改API基础URL

如果需要修改API基础URL，请更新：

1. `nginx.conf`中的代理路径
2. 前端代码中的`API_BASE_URL`常量
