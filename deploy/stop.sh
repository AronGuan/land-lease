#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
PY=".venv/bin/python"
PIP=".venv/bin/pip"

if [ -f .pid ]; then
  kill "$(cat .pid)" 2>/dev/null && echo "已停止 PID $(cat .pid)"
  rm -f .pid
else
  pkill -f "uvicorn landlease.app.main:app" && echo "已停止"
fi
