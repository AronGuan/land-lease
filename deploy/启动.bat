@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PY=.venv\Scripts\python.exe
set PIP=.venv\Scripts\pip.exe

echo 启动服务（后端 + 前端，单端口 8000）...
if not exist "%PY%" ( echo [错误] 尚未安装，请先运行「安装.bat」 & pause & exit /b 1 )

start "landlease-backend" /min "%PY%" -m uvicorn landlease.app.main:app --host 127.0.0.1 --port 8000 --log-level warning

echo 等待服务就绪 ...
set OK=0
for /l %%i in (1,1,30) do (
  timeout /t 1 >nul
  curl -s -o nul http://127.0.0.1:8000/api/health && set OK=1 && goto :ready
)
:ready
if "%OK%"=="1" (
  echo 服务已就绪，正在打开浏览器 ...
  start http://127.0.0.1:8000
) else (
  echo [警告] 30 秒内未通过健康检查，请查看 logs\backend.log 或手工检查 .env
)
pause
