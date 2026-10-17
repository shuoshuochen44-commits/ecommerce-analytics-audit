@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo 还没有准备好运行环境，请把此提示发给我协助安装。
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m zhishu_inspection.launcher
if errorlevel 1 pause
