#!/bin/bash

# CharacterLLM Framework - 停止服务脚本
# 用途：停止所有服务
# 使用：在容器内执行 /tmp/stop.sh

echo "=========================================="
echo "CharacterLLM Framework - 停止服务"
echo "=========================================="
echo ""

# ========== 停止后端 ==========
echo "🛑 停止后端服务..."

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
        echo "✅ 已停止后端进程 (PID: $OLD_PID)"
    fi
    rm -f /CharacterLLM_framework/backend.pid
fi

# ========== 停止前端 ==========
echo "🛑 停止前端服务..."

if pgrep nginx > /dev/null; then
    service nginx stop
    pkill -9 nginx 2>/dev/null
    echo "✅ Nginx 已停止"
else
    echo "ℹ️  Nginx 未运行"
fi

echo ""
echo "=========================================="
echo "✅ 所有服务已停止"
echo "=========================================="
echo ""

# 验证
echo "验证服务状态："
if ! pgrep -f "python.*run_with_env" > /dev/null && ! pgrep nginx > /dev/null; then
    echo "✓ 所有服务已完全停止"
else
    echo "⚠️  仍有进程在运行："
    ps aux | grep -E "python.*run_with_env|nginx" | grep -v grep
fi