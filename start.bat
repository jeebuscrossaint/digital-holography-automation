@echo off
cd /d "%~dp0"

where uv >nul 2>nul
if %errorlevel%==0 (
    uv run python main.py
) else if exist .venv\Scripts\python.exe (
    .venv\Scripts\python.exe main.py
) else if exist venv\Scripts\python.exe (
    venv\Scripts\python.exe main.py
) else (
    python main.py
)
