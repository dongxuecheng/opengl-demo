#!/bin/bash
# API 服务快速启动脚本

set -e

echo "================================================"
echo "  GPU 视频渲染 API 服务"
echo "================================================"
echo ""

# 检查 Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker 未安装"
    exit 1
fi

# 检查 NVIDIA Docker
if ! docker run --rm --gpus all nvidia/cuda:13.0.2-base-ubuntu22.04 nvidia-smi &> /dev/null; then
    echo "❌ NVIDIA Docker 未配置"
    exit 1
fi

echo "✅ 环境检查通过"
echo ""

# 构建镜像
echo "📦 构建 Docker 镜像..."
docker build -t video-renderer-api .

echo ""
echo "🚀 启动 API 服务..."
docker run --rm -it \
  --name video-renderer-api \
  --gpus all \
  --device /dev/dri:/dev/dri \
  -e NVIDIA_DRIVER_CAPABILITIES=all \
  -e NVIDIA_VISIBLE_DEVICES=all \
  -v "$(pwd)":/app \
  -p 8000:8000 \
  video-renderer-api

echo ""
echo "================================================"
echo "  服务已停止"
echo "================================================"
