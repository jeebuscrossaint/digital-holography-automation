@echo off
cd /d "%~dp0"

REM Point the Python sidecar at the project venv if it exists
if exist "%~dp0.venv\Scripts\python.exe" set "HOLOGRAPHY_PYTHON=%~dp0.venv\Scripts\python.exe"

REM --- Force node + cargo onto PATH for THIS process and all its children ---
REM npm/tauri spawn child processes that must find `node` and `cargo`. We avoid
REM `where` here on purpose: where.exe lives in System32, which isn't reliably
REM on this PATH, so `where` itself can fail. `if exist` is a cmd builtin and
REM always works.
set "NODEDIR=%USERPROFILE%\scoop\apps\nodejs\current"
if exist "%NODEDIR%\node.exe" set "PATH=%NODEDIR%;%PATH%"
set "CARGODIR=%USERPROFILE%\scoop\apps\rustup\current\.cargo\bin"
if exist "%CARGODIR%\cargo.exe" set "PATH=%CARGODIR%;%PATH%"
REM keep System32 reachable for child tools, in case it isn't already
set "PATH=%PATH%;%SystemRoot%\System32"

if not exist "%NODEDIR%\node.exe" (
    echo ERROR: node.exe not found at "%NODEDIR%".
    echo Install Node ^(scoop install nodejs^) or edit NODEDIR in this script.
    exit /b 1
)

cd app

REM Fresh-install deps if missing (a cloud-synced node_modules has broken shims
REM / unbuilt native deps). Safe + fast to skip when already present.
if not exist "node_modules\@tauri-apps\cli\tauri.js" (
    echo Installing frontend dependencies ^(first run on this machine^)...
    call npm install --no-audit --no-fund || ( echo npm install failed & exit /b 1 )
)

call npm run tauri dev
