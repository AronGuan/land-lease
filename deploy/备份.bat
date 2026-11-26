@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PY=.venv\Scripts\python.exe
set PIP=.venv\Scripts\pip.exe

set STAMP=%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%
set STAMP=%STAMP: =0%
set DIR=backup\%STAMP%
mkdir "%DIR%" 2>nul

echo 备份数据库 ...
set /p DBPW=<nul
for /f "tokens=1,2 delims==" %%a in ('findstr /b DB_PASSWORD .env') do set DBPW=%%b
for /f "tokens=1,2 delims==" %%a in ('findstr /b DB_USER .env') do set DBUSER=%%b
for /f "tokens=1,2 delims==" %%a in ('findstr /b DB_NAME .env') do set DBNAME=%%b
mysqldump -u%DBUSER% -p%DBPW% --single-transaction --routines %DBNAME% > "%DIR%\landlease.sql"

echo 备份原件与上传文件 ...
if exist storage xcopy /E /I /Y storage "%DIR%\storage" >nul

echo 备份完成：%DIR%
echo   含 landlease.sql（全库）与 storage\（合同原件）
pause
