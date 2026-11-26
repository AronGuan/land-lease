#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
PY=".venv/bin/python"
PIP=".venv/bin/pip"

STAMP=$(date +%Y%m%d_%H%M)
DIR="backup/$STAMP"
mkdir -p "$DIR"

DB_USER=$(grep -E '^DB_USER=' .env | cut -d= -f2)
DB_PASSWORD=$(grep -E '^DB_PASSWORD=' .env | cut -d= -f2)
DB_NAME=$(grep -E '^DB_NAME=' .env | cut -d= -f2)

mysqldump -u"$DB_USER" -p"$DB_PASSWORD" --single-transaction --routines "$DB_NAME" > "$DIR/landlease.sql"
[ -d storage ] && cp -r storage "$DIR/storage"

echo "备份完成：$DIR"
