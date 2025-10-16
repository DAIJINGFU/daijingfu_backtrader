#!/bin/bash
# 一键启动开发环境

echo "🚀 启动开发环境..."

# 启动后端
echo "📡 启动后端API服务..."
python backend/api_server.py &
BACKEND_PID=$!

# 等待后端启动
sleep 3

# 启动前端
echo "🎨 启动前端开发服务器..."
cd frontend
npm run dev &
FRONTEND_PID=$!

echo ""
echo "✅ 开发环境已启动！"
echo "📡 后端API: http://localhost:8000"
echo "🎨 前端页面: http://localhost:5173"
echo ""
echo "按 Ctrl+C 停止所有服务"

# 等待用户中断
trap "kill $BACKEND_PID $FRONTEND_PID; exit" INT
wait
