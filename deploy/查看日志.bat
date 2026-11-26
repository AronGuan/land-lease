@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PY=.venv\Scripts\python.exe
set PIP=.venv\Scripts\pip.exe

echo 最近 200 行服务日志（logs\backend.log）：
echo.
if exist logs\backend.log (
  powershell -Command "Get-Content logs\backend.log -Tail 200"
) else (
  echo 未找到 logs\backend.log，服务可能未以日志方式启动
)
echo.
pause
