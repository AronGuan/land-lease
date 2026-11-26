@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PY=.venv\Scripts\python.exe
set PIP=.venv\Scripts\pip.exe

echo 停止服务 ...
taskkill /FI "WINDOWTITLE eq landlease-backend*" /F >nul 2>nul
for /f "tokens=2" %%p in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do taskkill /PID %%p /F >nul 2>nul
echo 已停止
timeout /t 2 >nul
