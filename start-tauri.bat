@echo off
cd /d "%~dp0"

REM Make sure the Python sidecar finds the project's venv
where uv >nul 2>nul
if %errorlevel%==0 (
    uv sync >nul
    set "HOLOGRAPHY_PYTHON=%~dp0.venv\Scripts\python.exe"
)

REM Resolve npm. Prefer PATH; otherwise call the Scoop nodejs install by full
REM path (its PATH entry only reaches NEW shells after `scoop reset nodejs`).
set "RUNNPM=npm"
where npm >nul 2>nul
if not %errorlevel%==0 (
    if exist "%USERPROFILE%\scoop\apps\nodejs\current\npm.cmd" (
        set "RUNNPM=%USERPROFILE%\scoop\apps\nodejs\current\npm.cmd"
    ) else (
        echo.
        echo ERROR: npm not found. Open a NEW terminal ^(scoop already added node
        echo        to PATH^), or install Node with: scoop install nodejs
        exit /b 1
    )
)

cd app
call "%RUNNPM%" run tauri dev
