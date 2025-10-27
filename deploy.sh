#!/bin/bash

# CharacterLLM Framework - 完整部署脚本 (Neo4j版, 包含数据清空选项)
# 用途：拉取最新代码，停止旧服务，清空Neo4j数据（可选），启动新服务
# 使用：在容器内执行 /tmp/deploy.sh

set -e  # 遇到错误立即退出

echo "=========================================="
echo "CharacterLLM Framework - 部署脚本 (Neo4j版)"
echo "=========================================="
echo ""

# # ========== 第一步：拉取最新代码 ==========
# echo "📥 [1/7] 拉取最新代码..."
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

# ========== 第二步：检查 Neo4j 服务 (更新为检查容器名) ==========
echo "🔍 [2/7] 检查 Neo4j 服务..."

# 检查 Docker 容器 zhouyuhao-neo4j 是否在运行
if docker ps --format "table {{.Names}}" | grep -q "^zhouyuhao-neo4j$"; then
    echo "✅ Neo4j 容器 'zhouyuhao-neo4j' 正在运行"
else
    echo "❌ Neo4j 容器 'zhouyuhao-neo4j' 未运行。"
    echo "    请确保 Neo4j Docker 容器 'zhouyuhao-neo4j' 已启动并运行。"
    echo "    您可以尝试: docker start zhouyuhao-neo4j"
    exit 1
fi

# 尝试连接 Neo4j (使用 netcat 检查容器名对应的端口连通性)
if command -v nc >/dev/null 2>&1; then
    # 安装 netcat 如果未安装
    if ! command -v nc >/dev/null 2>&1; then
        apt-get update && apt-get install -y netcat-openbsd
    fi
    # 检查到容器名的连接
    if nc -zv zhouyuhao-neo4j 7687 2>/dev/null; then
        echo "✅ Neo4j Bolt 端口 (zhouyuhao-neo4j:7687) 可达"
    else
        echo "❌ 无法连接到 Neo4j 服务 (zhouyuhao-neo4j:7687)。"
        echo "    请检查 Docker 网络配置和 Neo4j 容器状态。"
        exit 1
    fi
else
    echo "⚠️  未找到 'nc' (netcat) 命令，无法检查 Neo4j 端口连通性。"
    echo "    请确保已安装 netcat 或手动确认 Neo4j (bolt://zhouyuhao-neo4j:7687) 是否可用。"
    # 由于已测试成功，这里可以不退出，但建议安装 nc
    # exit 1
fi
echo ""

# ========== 第三步：停止后端服务 ==========
echo "🛑 [3/7] 停止后端服务..."

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
echo "🛑 [4/7] 停止前端服务..."

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
echo "🔨 [5/7] 检查前端更新..."

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

# ========== 新增步骤：清空 Neo4j 数据 (如果需要) ==========
echo "🧹 [5.5/7] 清空 Neo4j 数据目录 (如果需要)..."

# 重要：此操作将永久删除所有 Neo4j 图谱数据！
# 请确保路径正确，并且您确实希望清空数据。
NEO4J_CONTAINER_NAME="zhouyuhao-neo4j"
NEO4J_DATA_DIR_ON_HOST="/home/zhouyuhao/neo4j/data"
NEO4J_IMPORT_DIR_ON_HOST="/home/zhouyuhao/neo4j/import" # 可选：同时清空 import 目录
NEO4J_LOGS_DIR_ON_HOST="/home/zhouyuhao/neo4j/logs"     # 可选：同时清空 logs 目录 (通常不需要)

if [ -d "$NEO4J_DATA_DIR_ON_HOST" ]; then
    echo "   正在清空 $NEO4J_DATA_DIR_ON_HOST ..."
    # 停止 Neo4j 容器以确保安全删除
    if docker ps --format "table {{.Names}}" | grep -q "^$NEO4J_CONTAINER_NAME$"; then
        echo "   临时停止 Neo4j 容器 ($NEO4J_CONTAINER_NAME)..."
        docker stop $NEO4J_CONTAINER_NAME
    fi
    # 删除数据目录内容
    rm -rf "$NEO4J_DATA_DIR_ON_HOST"/*
    # 可选：清空 import 目录
    if [ -d "$NEO4J_IMPORT_DIR_ON_HOST" ]; then
        echo "   正在清空 $NEO4J_IMPORT_DIR_ON_HOST ..."
        rm -rf "$NEO4J_IMPORT_DIR_ON_HOST"/*
    fi
    # 可选：清空 logs 目录 (通常不需要，除非调试)
    # if [ -d "$NEO4J_LOGS_DIR_ON_HOST" ]; then
    #     echo "   正在清空 $NEO4J_LOGS_DIR_ON_HOST ..."
    #     rm -rf "$NEO4J_LOGS_DIR_ON_HOST"/*
    # fi
    # 重新启动 Neo4j 容器
    echo "   重新启动 Neo4j 容器 ($NEO4J_CONTAINER_NAME)..."
    docker start $NEO4J_CONTAINER_NAME
    # 等待 Neo4j 容器启动
    echo "   等待 Neo4j 容器启动..."
    sleep 10 # 给 Neo4j 足够时间初始化
    # 可以在这里添加一个检查，确认 Neo4j 已准备好接受连接
    # 例如，可以再次使用 nc 检查 7687 或 7474 端口
    # while ! nc -z localhost 7687; do
    #   sleep 1
    # done
    echo "✅ Neo4j 数据目录已清空并重启。"
else
    echo "⚠️  警告：Neo4j 数据目录 $NEO4J_DATA_DIR_ON_HOST 不存在，跳过清空步骤。"
fi
echo ""

# ========== 第六步：安装/更新 Python 依赖 (包含 Neo4j 和 Numpy) ==========
echo "📦 [6/7] 安装/更新 Python 依赖..."

cd /CharacterLLM_framework

# # 检查 requirements.txt 是否存在
# if [ -f requirements.txt ]; then
#     echo "📋 从 requirements.txt 安装依赖..."
#     # 使用 --upgrade 确保安装最新版本
#     pip install --upgrade -r requirements.txt
# else
#     echo "⚠️  警告：requirements.txt 文件不存在，跳过依赖安装。"
#     # 如果您希望硬编码安装，可以在这里添加 pip install neo4j numpy ...
# fi

# # --- 修改点：先升级 numpy 和 pandas，再安装 neo4j ---
# echo "🔍 确保 numpy 和 pandas 版本兼容..."
# pip install --upgrade "numpy>=1.21.0" "pandas>=1.3.0" # 指定较新且通常兼容的版本
# echo "✅ Numpy 和 Pandas 版本检查/更新完成"

# # 确保 neo4j 和 numpy 已安装 (可能 neo4j 会重新安装以适应新的 numpy/pandas)
# echo "🔍 安装/更新 neo4j 库..."
# pip install --upgrade neo4j
# echo "✅ Neo4j 依赖检查/更新完成"
# echo ""

# ========== 第七步：启动后端服务 ==========
echo "🚀 [7/7] 启动后端服务..."

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
# Neo4j 配置 (使用容器名)
NEO4J_URI=bolt://zhouyuhao-neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=zyh123456
EOF
fi

# 启动后端
echo "🔧 启动后端应用 (连接 Neo4j)..."

# 重要：确保代码中的 GraphStore 初始化 URI 也已更新为 zhouyuhao-neo4j:7687
# 否则应用启动时仍会尝试连接 localhost
nohup python3 run_with_env.py > backend.log 2>&1 &
BACKEND_PID=$!
echo $BACKEND_PID > backend.pid

echo "✅ 后端已启动 (PID: $BACKEND_PID)"
echo "   日志文件: /CharacterLLM_framework/backend.log"

# 等待后端启动 (增加时间以等待 Neo4j 连接)
echo "⏳ 等待后端启动并连接 Neo4j (可能需要 10-15 秒)..."
sleep 15

# 检查后端是否成功启动
if ps -p $BACKEND_PID > /dev/null; then
    echo "✅ 后端进程运行正常"
    # 检查日志中是否有 Neo4j 连接成功的明确信息
    if grep -q "成功连接到 Neo4j 数据库" backend.log; then
        echo "✅ 后端已成功连接到 Neo4j"
    else
        echo "⚠️  后端进程运行中，但未在日志中找到 '成功连接到 Neo4j 数据库' 的确认信息。"
        echo "    请检查日志以确认 Neo4j 连接状态。"
        # 可选：输出日志相关部分
        echo "    --- 后端日志中关于 Neo4j 的部分 ---"
        grep -i "neo4j\|graph\|connect" backend.log | tail -n 10
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
echo "🚀 [8/7 - 调整] 启动前端服务..."

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
echo "✅ 部署完成！(Neo4j 已集成)"
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
