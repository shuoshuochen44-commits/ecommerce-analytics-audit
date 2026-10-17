@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Python environment missing. Follow README.md to create .venv first.
  pause
  exit /b 1
)
if not exist "artifacts\analytics\latest.json" (
  echo Building first snapshot...
  ".venv\Scripts\python.exe" -m zhishu_inspection.pipeline "data\raw\olist" "artifacts\analytics"
  if errorlevel 1 (
    pause
    exit /b 1
  )
)
echo Open http://127.0.0.1:8765 in your browser. Keep this window open.
".venv\Scripts\python.exe" -m zhishu_inspection.server "artifacts\analytics" --port 8765
pause
