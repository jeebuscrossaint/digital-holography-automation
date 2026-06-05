@echo off
REM Web-app server: serves the React UI + the hardware API on one port.
REM Run this on the lab NUC, then open it from any browser on your tailnet
REM (e.g. http://<nuc-name>:8000). The experiment runs in a background thread
REM on the server, so it keeps going after you close the browser / disconnect.
cd /d "%~dp0"

REM node (only needed to build the UI the first time)
set "NODEDIR=%USERPROFILE%\scoop\apps\nodejs\current"
if exist "%NODEDIR%\node.exe" set "PATH=%NODEDIR%;%PATH%"

REM Make sure the Python deps (fastapi/uvicorn/...) are installed
where uv >nul 2>nul && uv sync >nul 2>nul

REM Build the web UI if it isn't built yet (produces app\dist)
if not exist "app\dist\index.html" (
    echo Building web UI ^(first run on this machine^)...
    pushd app
    if not exist "node_modules\vite" call npm install --no-audit --no-fund
    node node_modules\vite\bin\vite.js build || ( echo UI build failed & popd & exit /b 1 )
    popd
)

if not "%~1"=="" ( set "PORT=%~1" ) else ( set "PORT=8000" )
echo.
echo Serving on http://0.0.0.0:%PORT%  (open it from your tailnet, e.g. http://%COMPUTERNAME%:%PORT%)
echo Press Ctrl+C to stop.
echo.
".venv\Scripts\python.exe" -m uvicorn server.main:app --host 0.0.0.0 --port %PORT%
