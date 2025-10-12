#!/bin/bash

# CharacterLLM Framework - 完整部署脚本
# 用途：拉取最新代码，停止旧服务，启动新服务
# 使用：在容器内执行 /tmp/deploy.sh

set -e  # 遇到错误立即退出

echo "=========================================="
echo "CharacterLLM Framework - 部署脚本"
echo "=========================================="
echo ""

# # ========== 第一步：拉取最新代码 ==========
# echo "📥 [1/6] 拉取最新代码..."
# cd /CharacterLLM_framework

# # 检查是否有未提交的修改
# if [[ -n $(git status -s) ]]; then
#     echo "⚠️  警告：有未提交的修改"
#     git status -s
#     read -p "是否继续？(y/n) " -n 1 -r
#     echo
#     if [[ ! $REPLY =~ ^[Yy]$ ]]; then
#         echo "❌ 部署已取消"
#         exit 1
#     fi
# fi

# # 拉取最新代码
# git pull origin main
# echo "✅ 代码已更新"
# echo ""

# ========== 第二步：停止后端服务 ==========
echo "🛑 [2/6] 停止后端服务..."

# 查找并停止 Python 后端进程
if pgrep -f "python.*run_with_env.py" > /dev/null; then
    pkill -f "python.*run_with_env.py"
    echo "✅ 后端进程已停止"
    sleep 2
else
    echo "ℹ️  后端未运行"
fi

# 检查 PID 文件
if [ -f /CharacterLLM_framework/backend.pid ]; then
    OLD_PID=$(cat /CharacterLLM_framework/backend.pid)
    if ps -p $OLD_PID > /dev/null 2>&1; then
        kill $OLD_PID
        echo "✅ 已停止旧的后端进程 (PID: $OLD_PID)"
    fi
    rm -f /CharacterLLM_framework/backend.pid
fi

echo ""

# ========== 第三步：停止前端服务 ==========
echo "🛑 [3/6] 停止前端服务..."

# 停止 Nginx
if pgrep nginx > /dev/null; then
    service nginx stop
    pkill -9 nginx 2>/dev/null
    echo "✅ Nginx 已停止"
else
    echo "ℹ️  Nginx 未运行"
fi

echo ""

# ========== 第四步：重新构建前端（如果有更新）==========
echo "🔨 [4/6] 检查前端更新..."

cd /CharacterLLM_framework/frontend/character-llm-frontend

# 检查前端文件是否有更新
if git diff --name-only HEAD@{1} HEAD | grep -q "^frontend/"; then
    echo "📦 前端有更新，重新构建..."
    
    # 安装依赖（如果 package.json 有更新）
    if git diff --name-only HEAD@{1} HEAD | grep -q "package.json"; then
        echo "📦 安装前端依赖..."
        npm install --legacy-peer-deps
    fi
    
    # 构建前端
    echo "🔨 构建前端..."
    npm run build
    
    # 部署到 Nginx
    echo "📋 部署前端文件..."
    rm -rf /usr/share/nginx/html/*
    cp -r dist/* /usr/share/nginx/html/
    
    echo "✅ 前端已重新构建和部署"
else
    echo "ℹ️  前端无更新，跳过构建"
fi

echo ""

# ========== 第五步：启动后端服务 ==========
echo "🚀 [5/6] 启动后端服务..."

cd /CharacterLLM_framework

# 检查环境变量文件
if [ ! -f .env ]; then
    echo "⚠️  警告：.env 文件不存在"
    echo "创建默认 .env 文件..."
    cat > .env << 'EOF'
OPENAI_API_KEY=sk-zk2fbc13c9dacbd9d1c577991155e25fa2568e256f5de463
OPENAI_BASE_URL=https://api.zhizengzeng.com/v1
DATABASE_URL=sqlite:///./character_llm.db
DEBUG=false
CORS_ORIGINS=["http://localhost:3000","http://localhost:5173","http://localhost:80","http://localhost:9000"]
CHROMA_PERSIST_DIRECTORY=./chroma_db
EOF
fi

# 启动后端
nohup python3 run_with_env.py > backend.log 2>&1 &
BACKEND_PID=$!
echo $BACKEND_PID > backend.pid

echo "✅ 后端已启动 (PID: $BACKEND_PID)"
echo "   日志文件: /CharacterLLM_framework/backend.log"

# 等待后端启动
echo "⏳ 等待后端启动..."
sleep 5

# 检查后端是否成功启动
if ps -p $BACKEND_PID > /dev/null; then
    echo "✅ 后端进程运行正常"
else
    echo "❌ 后端启动失败！"
    echo "查看日志："
    tail -n 30 backend.log
    exit 1
fi

echo ""

# ========== 第六步：启动前端服务 ==========
echo "🚀 [6/6] 启动前端服务..."

# 启动 Nginx
service nginx start

if pgrep nginx > /dev/null; then
    echo "✅ Nginx 已启动"
else
    echo "❌ Nginx 启动失败！"
    nginx -t
    exit 1
fi

echo ""

# ========== 验证部署 ==========
echo "=========================================="
echo "🔍 验证部署..."
echo "=========================================="
echo ""

# 测试后端
echo "测试后端 API..."
if curl -s http://localhost:8000/health > /dev/null; then
    echo "✅ 后端 API 正常"
    curl -s http://localhost:8000/health
    echo ""
else
    echo "❌ 后端 API 无响应"
fi

# 测试前端
echo ""
echo "测试前端..."
if curl -s -I http://localhost:80 | grep -q "200 OK"; then
    echo "✅ 前端服务正常"
else
    echo "⚠️  前端可能未正常启动"
fi

# 显示服务状态
echo ""
echo "=========================================="
echo "📊 服务状态"
echo "=========================================="
echo ""
echo "后端进程："
ps aux | grep "python.*run_with_env" | grep -v grep || echo "  未找到后端进程"
echo ""
echo "Nginx 进程："
ps aux | grep nginx | grep -v grep || echo "  未找到 Nginx 进程"
echo ""
echo "端口监听："
netstat -tlnp 2>/dev/null | grep -E "8000|:80" || echo "  未找到监听端口"

# 显示最新日志
echo ""
echo "=========================================="
echo "📋 最新后端日志（最后 20 行）"
echo "=========================================="
tail -n 20 /CharacterLLM_framework/backend.log

# 显示访问信息
echo ""
echo "=========================================="
echo "✅ 部署完成！"
echo "=========================================="
echo ""
echo "📍 容器内访问地址："
echo "   后端 API: http://localhost:8000"
echo "   API 文档: http://localhost:8000/docs"
echo "   前端界面: http://localhost:80"
echo ""
echo "📍 宿主机访问地址："
echo "   后端 API: http://localhost:8086"
echo "   API 文档: http://localhost:8086/docs"
echo "   前端界面: http://localhost:9000"
echo ""
echo "📝 查看日志："
echo "   tail -f /CharacterLLM_framework/backend.log"
echo ""
echo "🔄 重新部署："
echo "   /deploy.sh"
echo ""
echo "=========================================="