@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PY=.venv\Scripts\python.exe
set PIP=.venv\Scripts\pip.exe

echo ============================================
echo  国有土地租赁智能管理系统 - 一键安装
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [错误] 未检测到 Python，请先安装 Python 3.12+ 并勾选 Add to PATH
  pause & exit /b 1
)

echo [1/5] 创建虚拟环境 .venv ...
if not exist ".venv" python -m venv .venv

echo [2/5] 安装依赖 ...
if exist "wheels" (
  echo       检测到 wheels 目录，使用离线安装
  "%PIP%" install --no-index --find-links=wheels -r requirements.txt
) else (
  echo       未检测到 wheels，使用在线安装（需可访问 PyPI）
  "%PIP%" install -r requirements.txt
)

echo [3/5] 准备配置文件 .env ...
if not exist ".env" (
  copy /Y .env.example .env >nul
  echo       已生成 .env，请编辑填写 DB_PASSWORD 与 DASHSCOPE_API_KEY
  notepad .env
) else (
  echo       .env 已存在，跳过
)

echo [4/5] 创建数据库 ...
echo       若未自动创建，请手工执行：
echo         CREATE DATABASE landlease DEFAULT CHARSET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
echo       表结构在首次启动时自动创建（27 张表），也可手工执行 docs/schema.sql

echo [5/5] 安装完成
echo.
echo 下一步：
echo   1. 确认 .env 中的 DB_PASSWORD 已填写、MySQL 已启动
echo   2. 双击「启动.bat」
echo   3. 浏览器打开 http://127.0.0.1:8000
echo.
pause
