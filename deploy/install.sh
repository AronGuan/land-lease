#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
PY=".venv/bin/python"
PIP=".venv/bin/pip"

echo "===== 国有土地租赁智能管理系统 - 一键安装 ====="

if ! command -v python3 >/dev/null; then
  echo "[错误] 未检测到 python3"; exit 1
fi

echo "[1/5] 创建虚拟环境 .venv ..."
[ -d .venv ] || python3 -m venv .venv

echo "[2/5] 安装依赖 ..."
if [ -d wheels ]; then
  "$PIP" install --no-index --find-links=wheels -r requirements.txt
else
  "$PIP" install -r requirements.txt
fi

echo "[3/5] 准备配置文件 .env ..."
if [ ! -f .env ]; then
  cp .env.example .env
  echo "已生成 .env，请编辑填写 DB_PASSWORD 与 DASHSCOPE_API_KEY"
fi

echo "[4/5] 创建数据库（需 mysql 客户端） ..."
echo "  CREATE DATABASE landlease DEFAULT CHARSET utf8mb4 COLLATE utf8mb4_0900_ai_ci;"
echo "  表结构在首次启动时自动创建（27 张表）"

echo "[5/5] 安装完成。下一步：编辑 .env，然后 ./start.sh"
