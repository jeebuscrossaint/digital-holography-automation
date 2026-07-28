# Holography Testbed - Quick Test Script
# Activates environment and sets up paths

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Add Xeneth DLL to PATH
$env:PATH += ";C:\Program Files\Common Files\XenICs\Runtime"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "HOLOGRAPHY TESTBED - TESTING ENVIRONMENT" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Environment ready! Available test commands:" -ForegroundColor Green
Write-Host ""
Write-Host "  uv run pytest                             # Run the test suite"
Write-Host "  python tools/probe_switch.py              # Probe the fiber switch"
Write-Host "  python tools/probe_mpc.py                 # Probe the MPC320 paddles"
Write-Host "  python main.py                            # Launch the app"
Write-Host ""
Write-Host "NOTE: If the camera 'connects' but shows no frames, it is the" -ForegroundColor Yellow
Write-Host "      Windows Firewall blocking inbound GigE (GVSP) for python.exe." -ForegroundColor Yellow
Write-Host "      Run tools/setup_lab_machine.ps1 once. (It is NOT a light issue.)" -ForegroundColor Yellow
Write-Host ""
