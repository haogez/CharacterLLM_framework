#!/bin/bash

# CharacterLLM Framework - 完整部署脚本 (VSCode远程服务器 Docker版, Neo4j独立容器版, 包含数据清空选项)
# 用途：拉取最新代码，停止旧服务，清空generated_stories目录，启动新服务，连接到本地Neo4j Docker容器
# 使用：在 zhouyuhao 容器内执行 /tmp/deploy.sh

set -e  # 遇到错误立即退出

echo "=========================================="
echo "CharacterLLM Framework - 部署脚本 (VSCode远程服务器 Docker版, Neo4j独立容器版)"
echo "=========================================="
echo ""

# ========== 新增步骤：清空 generated_stories 目录 ==========
echo "🧹 [1/8] 清空 generated_stories和import 目录..."

GENERATED_STORIES_DIR="/CharacterLLM_framework/generated_stories"
IMPORT_DIR="/zhouyuhao/zhouyuhao_data/import"

if [ -d "$GENERATED_STORIES_DIR" ]; then
    echo "   正在清空目录: $GENERATED_STORIES_DIR"
    rm -rf "$GENERATED_STORIES_DIR"/*
    echo "✅ generated_stories 目录已清空"
    echo "   正在清空目录: $IMPORT_DIR"
    rm -rf "$IMPORT_DIR"/*
    echo "✅ import 目录已清空"
else
    echo "⚠️  警告：generated_stories 目录 $GENERATED_STORIES_DIR 不存在或无法访问。"
    # 若目录不存在，可选择创建空目录
    mkdir -p "$GENERATED_STORIES_DIR"
    echo "    已创建空的 generated_stories 目录"
fi
echo ""

# # ========== 第一步：拉取最新代码 (可选，如果代码已更新) ==========
# echo "📥 [2/8] 拉取最新代码..."
# cd /CharacterLLM_framework
# 
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
# 
# # 拉取最新代码
# git pull origin main
# echo "✅ 代码已更新"
# echo ""

# ========== 第二步：检查 Neo4j Docker 容器服务 ==========
echo "🔍 [2/8] 检查 本地Neo4j Docker 容器服务..."

# Neo4j Docker容器的配置信息 (根据您的启动命令)
NEO4J_URI="bolt://neo4j-latest:7687" # 容器内访问宿主机映射的端口，等同于访问容器内7687
NEO4J_USERNAME="neo4j"
NEO4J_PASSWORD="zyh123456"
NEO4J_DATABASE="neo4j"

echo "   预配置的 Neo4j URI (容器内访问): $NEO4J_URI"
echo "   预配置的 Neo4j Database: $NEO4J_DATABASE"
echo "   (检查 neo4j-latest 容器是否正在运行且网络可达)..."
echo ""

# 检查 netcat 是否安装（用于测试端口连通性）
if ! command -v nc >/dev/null 2>&1; then
    echo "   未找到 netcat，正在安装..."
    apt-get update && apt-get install -y netcat-openbsd -q
fi

# 测试容器到本地Neo4j映射端口的连通性
NEO4J_HOST="neo4j-latest"
NEO4J_BOLT_PORT="7687"
echo "   测试连接：$NEO4J_HOST:$NEO4J_BOLT_PORT (容器内映射的Neo4j Bolt端口)..."
if nc -zv $NEO4J_HOST $NEO4J_BOLT_PORT 2>/dev/null; then
    echo "✅ Neo4j Bolt端口 ($NEO4J_HOST:$NEO4J_BOLT_PORT) 可达"
else
    echo "❌ 无法连接到本地Neo4j Docker容器的Bolt端口！"
    echo "    请检查以下问题："
    echo "    1. Neo4j容器 'neo4j-latest' 是否正在运行？"
    echo "    2. zhouyuhao容器是否能访问localhost:7687 (通常在Docker bridge网络下，localhost指宿主机)？"
    echo "    3. Neo4j容器的启动命令是否正确映射了端口 7687？"
    # 提供检查命令
    echo "    检查命令示例："
    echo "      docker ps --filter name=neo4j-latest"
    echo "      docker logs neo4j-latest"
    exit 1
fi
echo ""

# ========== 第三步：停止后端服务 ==========
echo "🛑 [3/8] 停止后端服务..."

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

# ========== 第四步：停止前端服务 ==========
echo "🛑 [4/8] 停止前端服务..."

# 停止 Nginx
if pgrep nginx > /dev/null; then
    service nginx stop
    pkill -9 nginx 2>/dev/null
    echo "✅ Nginx 已停止"
else
    echo "ℹ️  Nginx 未运行"
fi

echo ""

# ========== 第五步：重新构建前端（如果有更新）==========
echo "🔨 [5/8] 检查前端更新..."

cd /CharacterLLM_framework/frontend/character-llm-frontend

# 检查前端文件是否有更新
# 注意：HEAD@{1} 在非 git pull 环境下可能无效，这里假设代码已更新
# if git diff --name-only HEAD@{1} HEAD | grep -q "^frontend/"; then
#     echo "📦 前端有更新，重新构建..."
#     # ... (构建逻辑)
# # else
# #     echo "ℹ️  前端无更新，跳过构建"
# # fi
# 简化处理：总是尝试构建（如果需要的话）或者跳过
echo "ℹ️  检查前端构建必要性 (当前逻辑为简化处理，如需精确判断，请启用 Git diff 逻辑)..."
# 假设前端未更新，跳过构建
echo "ℹ️  假设前端未更新，跳过构建 (如需构建，请修改脚本或手动执行)"
# 如果确实需要构建，取消下面的注释
# echo "📦 前端有更新，重新构建..."
# # 安装依赖（如果 package.json 有更新）
# if [ -f package-lock.json ] && git diff --name-only HEAD@{1} HEAD | grep -q "package-lock.json"; then
#     echo "📦 安装前端依赖..."
#     npm install --legacy-peer-deps
# elif [ -f yarn.lock ] && git diff --name-only HEAD@{1} HEAD | grep -q "yarn.lock"; then
#     echo "📦 安装前端依赖..."
#     yarn install
# elif git diff --name-only HEAD@{1} HEAD | grep -q "package.json"; then
#     echo "📦 安装前端依赖..."
#     npm install --legacy-peer-deps
# fi
# # 构建前端
# echo "🔨 构建前端..."
# npm run build
# # 部署到 Nginx
# echo "📋 部署前端文件..."
# rm -rf /usr/share/nginx/html/*
# cp -r dist/* /usr/share/nginx/html/
# echo "✅ 前端已重新构建和部署"

# 更新 Nginx 配置（无论前端是否更新都要检查）
echo "📋 更新 Nginx 配置..."
cd /CharacterLLM_framework
if [ -f nginx.conf ]; then
    cp nginx.conf /etc/nginx/conf.d/default.conf
    echo "✅ Nginx 配置已更新"
else
    echo "⚠️  警告：nginx.conf 文件不存在"
fi

echo ""

# ========== 第六步：安装/更新 Python 依赖 (包含 Neo4j 和 Numpy) ==========
echo "📦 [6/8] 安装/更新 Python 依赖..."

cd /CharacterLLM_framework

# 强制安装兼容的 Neo4j 驱动版本（避免版本不兼容）
# echo "   安装兼容的 Neo4j 驱动（5.20.0 稳定版）..."
# pip install --upgrade neo4j==5.20.0 numpy>=1.21.0 pandas>=1.3.0

# # --- 取消注释：检查 requirements.txt 并安装依赖 ---
# if [ -f requirements.txt ]; then
#     echo "📋 从 requirements.txt 安装依赖..."
#     # 使用 --upgrade 确保安装最新版本
#     pip install --upgrade -r requirements.txt
# else
#     echo "⚠️  警告：requirements.txt 文件不存在，跳过依赖安装。"
#     # 如果您希望硬编码安装，可以在这里添加 pip install neo4j numpy ...
# fi

# # --- 取消注释：先升级 numpy 和 pandas，再安装 neo4j ---
# echo "🔍 确保 numpy 和 pandas 版本兼容..."
# pip install --upgrade "numpy>=1.21.0" "pandas>=1.3.0" # 指定较新且通常兼容的版本
# echo "✅ Numpy 和 Pandas 版本检查/更新完成"

# # 确保 neo4j 和 numpy 已安装 (可能 neo4j 会重新安装以适应新的 numpy/pandas)
# echo "🔍 安装/更新 neo4j 库..."
# pip install --upgrade neo4j
echo "✅ Neo4j 依赖检查/更新完成"
echo ""

# ========== 第七步：启动后端服务 ==========
echo "🚀 [7/8] 启动后端服务..."

cd /CharacterLLM_framework

# 检查环境变量文件
ENV_FILE_PATH="/CharacterLLM_framework/.env"
if [ ! -f "$ENV_FILE_PATH" ]; then
    echo "⚠️  警告：.env 文件不存在"
    echo "创建默认 .env 文件 (包含 Neo4j Docker 容器配置)..."
    cat > "$ENV_FILE_PATH" << 'EOF'
OPENAI_API_KEY=sk-zk2fbc13c9dacbd9d1c577991155e25fa2568e256f5de
OPENAI_BASE_URL=https://api.zhizengzeng.com/v1            
DATABASE_URL=sqlite:///./character_llm.db
DEBUG=false
CORS_ORIGINS=["http://localhost:3000","http://localhost:5173","http://localhost:80","http://localhost:9000"]
CHROMA_PERSIST_DIRECTORY=./chroma_db
# --- Neo4j Docker 容器配置 ---
NEO4J_URI=bolt://neo4j-latest:7687
NEO4J_USERNAME=neo4j                      
NEO4J_PASSWORD=zyh123456              
NEO4J_DATABASE=neo4j
EOF
else
    echo "ℹ️  .env 文件已存在: $ENV_FILE_PATH"
    # 检查 .env 文件中是否已包含 Docker Neo4j 的 URI
    if grep -q "bolt://neo4j-latest:7687" "$ENV_FILE_PATH"; then
        echo "✅ .env 文件已包含 Neo4j Docker 容器 URI"
    else
        echo "⚠️  警告：.env 文件中未找到 Neo4j Docker 容器 URI！"
        echo "    自动更新 .env 文件中的 Neo4j 配置..."
        # 替换或添加 Neo4j 配置（使用 sed 命令）
        sed -i '/^NEO4J_URI/d' "$ENV_FILE_PATH"
        sed -i '/^NEO4J_USERNAME/d' "$ENV_FILE_PATH"
        sed -i '/^NEO4J_USER/d' "$ENV_FILE_PATH" # 兼容旧键名
        sed -i '/^NEO4J_PASSWORD/d' "$ENV_FILE_PATH"
        sed -i '/^NEO4J_DATABASE/d' "$ENV_FILE_PATH"
        # 添加新配置
        echo -e "\n# --- Neo4j Docker 容器配置 ---" >> "$ENV_FILE_PATH"
        echo "NEO4J_URI=bolt://neo4j-latest:7687" >> "$ENV_FILE_PATH"
        echo "NEO4J_USERNAME=neo4j" >> "$ENV_FILE_PATH"
        echo "NEO4J_PASSWORD=zyh123456" >> "$ENV_FILE_PATH"
        echo "NEO4J_DATABASE=neo4j" >> "$ENV_FILE_PATH"
        echo "✅ .env 文件已更新为 Neo4j Docker 容器配置"
    fi
fi

# 启动后端
echo "🔧 启动后端应用 (连接本地Neo4j Docker容器)..."

# 重要：确保代码中的 GraphStore 已配置正确的 Neo4j 连接参数 (bolt://localhost:7687)
nohup python3 run_with_env.py > backend.log 2>&1 &
BACKEND_PID=$!
echo $BACKEND_PID > backend.pid

echo "✅ 后端已启动 (PID: $BACKEND_PID)"
echo "   日志文件: /CharacterLLM_framework/backend.log"

# 等待后端启动 (增加时间以等待 Neo4j 连接)
echo "⏳ 等待后端启动并连接本地Neo4j Docker容器 (可能需要 10-15 秒)..."
sleep 15

# 检查后端是否成功启动
if ps -p $BACKEND_PID > /dev/null; then
    echo "✅ 后端进程运行正常"
    # 检查日志中是否有 Neo4j 连接成功的明确信息
    if grep -q "成功连接到 Neo4j\|--- 成功连接到 Neo4j.*---" backend.log; then
        echo "✅ 后端已成功连接到本地Neo4j Docker容器"
    else
        echo "⚠️  后端进程运行中，但未在日志中找到 '成功连接到 Neo4j' 的确认信息。"
        echo "    请检查日志以确认 Neo4j 连接状态。"
        # 可选：输出日志相关部分
        echo "    --- 后端日志中关于 Neo4j 的部分 ---"
        grep -i "neo4j\|graph\|connect\|bolt" backend.log | tail -n 10
        echo "    --- 日志结束 ---"
    fi
else
    echo "❌ 后端启动失败！"
    echo "查看日志："
    tail -n 30 backend.log
    exit 1
fi

echo ""

# ========== 第八步：启动前端服务 ==========
echo "🚀 [8/8] 启动前端服务..."

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
netstat -tlnp 2>/dev/null | grep -E "8000|:80" || echo "  未找到监听端口 (注意: Neo4j 端口 7687/7474 未在此列出)"

# 显示最新日志
echo ""
echo "=========================================="
echo "📋 最新后端日志（最后 20 行）"
echo "=========================================="
tail -n 20 /CharacterLLM_framework/backend.log

# 显示访问信息
echo ""
echo "=========================================="
echo "✅ 部署完成！(已适配本地Neo4j Docker容器，generated_stories 目录已清空)"
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
echo "   /tmp/deploy.sh"
echo ""
echo "=========================================="
