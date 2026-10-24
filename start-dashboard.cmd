@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Please install the Python environment as described in README.md.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m zhishu_inspection.launcher
if errorlevel 1 pause
