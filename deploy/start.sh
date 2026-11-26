#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
PY=".venv/bin/python"
PIP=".venv/bin/pip"

mkdir -p logs
nohup "$PY" -m uvicorn landlease.app.main:app --host 127.0.0.1 --port 8000 \
  --log-level warning >> logs/backend.log 2>&1 &
echo $! > .pid

for i in $(seq 1 30); do
  sleep 1
  if curl -sf http://127.0.0.1:8000/api/health >/dev/null; then
    echo "服务已就绪：http://127.0.0.1:8000 （PID $(cat .pid)）"; exit 0
  fi
done
echo "[警告] 30 秒未通过健康检查，请看 logs/backend.log"
