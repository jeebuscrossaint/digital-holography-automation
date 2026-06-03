@echo off
cd /d "%~dp0"

REM Make sure the Python sidecar finds the project's venv
where uv >nul 2>nul
if %errorlevel%==0 (
    uv sync >nul
    set "HOLOGRAPHY_PYTHON=%~dp0.venv\Scripts\python.exe"
)

cd app
npm run tauri dev
