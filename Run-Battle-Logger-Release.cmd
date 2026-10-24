@echo off
setlocal
cd /d "%~dp0"
set PYTHONDONTWRITEBYTECODE=1
start "" pyw -3 -B "%~dp0src\release_app.py" %*
exit /b
