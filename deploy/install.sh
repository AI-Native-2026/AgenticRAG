#!/usr/bin/env bash
# 依赖安装（在 conda 环境已激活的前提下）
set -e
cd "$(dirname "$0")/../backend"
python -m pip install -r requirements.txt
echo "[install] 后端依赖安装完成"

# 可选：构建前端
if command -v npm >/dev/null 2>&1; then
  cd ../frontend
  npm install
  npm run build
  echo "[install] 前端已构建到 frontend/dist"
else
  echo "[install] 未检测到 npm，跳过前端构建"
fi
