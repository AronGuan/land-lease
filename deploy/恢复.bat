@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PY=.venv\Scripts\python.exe
set PIP=.venv\Scripts\pip.exe

echo 可恢复的备份：
dir /b backup 2>nul
echo.
set /p STAMP=请输入备份目录名（如 20261029_0030）：
if not defined STAMP ( echo 未输入，取消 & pause & exit /b 1 )
if not exist "backup\%STAMP%\landlease.sql" ( echo [错误] 备份不存在 & pause & exit /b 1 )

echo 警告：将覆盖当前数据库！
set /p CONF=确认请输入 YES：
if not "%CONF%"=="YES" ( echo 已取消 & pause & exit /b 1 )

for /f "tokens=1,2 delims==" %%a in ('findstr /b DB_PASSWORD .env') do set DBPW=%%b
for /f "tokens=1,2 delims==" %%a in ('findstr /b DB_USER .env') do set DBUSER=%%b
for /f "tokens=1,2 delims==" %%a in ('findstr /b DB_NAME .env') do set DBNAME=%%b

mysql -u%DBUSER% -p%DBPW% %DBNAME% < "backup\%STAMP%\landlease.sql"
if exist "backup\%STAMP%\storage" xcopy /E /I /Y "backup\%STAMP%\storage" storage >nul
echo 恢复完成，请重新启动服务
pause
