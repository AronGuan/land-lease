#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
PY=".venv/bin/python"
PIP=".venv/bin/pip"

ls -1 backup 2>/dev/null || { echo "无备份"; exit 1; }
read -p "请输入备份目录名： " STAMP
[ -f "backup/$STAMP/landlease.sql" ] || { echo "[错误] 备份不存在"; exit 1; }
read -p "将覆盖当前数据库，确认请输入 YES： " CONF
[ "$CONF" = "YES" ] || { echo "已取消"; exit 1; }

DB_USER=$(grep -E '^DB_USER=' .env | cut -d= -f2)
DB_PASSWORD=$(grep -E '^DB_PASSWORD=' .env | cut -d= -f2)
DB_NAME=$(grep -E '^DB_NAME=' .env | cut -d= -f2)

mysql -u"$DB_USER" -p"$DB_PASSWORD" "$DB_NAME" < "backup/$STAMP/landlease.sql"
[ -d "backup/$STAMP/storage" ] && cp -r "backup/$STAMP/storage" storage
echo "恢复完成，请重新启动服务"
