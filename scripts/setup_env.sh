#!/bin/bash
# 环境搭建脚本

echo "🚀 设置开发环境..."

# Python环境
echo "📦 设置Python环境..."
python -m venv venv
source venv/bin/activate
pip install -U pip
pip install -e .

# 前端环境
echo "📦 设置前端环境..."
cd frontend
npm install
cd ..

# 生成测试数据
echo "📊 生成测试数据..."
python scripts/generate_test_data.py

# 创建日志目录
mkdir -p logs

echo ""
echo "✅ 环境搭建完成！"
echo ""
echo "下一步:"
echo "1. source venv/bin/activate"
echo "2. ./scripts/start_dev.sh"
