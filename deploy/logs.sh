#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
PY=".venv/bin/python"
PIP=".venv/bin/pip"

tail -n 200 logs/backend.log 2>/dev/null || echo "未找到 logs/backend.log"
