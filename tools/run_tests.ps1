# Holography Testbed - Quick Test Script
# Activates environment and sets up paths

# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Add Xeneth DLL to PATH
$env:PATH += ";C:\Program Files\Common Files\XenICs\Runtime"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "HOLOGRAPHY TESTBED - TESTING ENVIRONMENT" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Environment ready! Available test commands:" -ForegroundColor Green
Write-Host ""
Write-Host "  python quick_camera_test.py          # Test camera only"
Write-Host "  python test_components.py --camera   # Test camera (detailed)"
Write-Host "  python test_components.py --all      # Test all hardware"
Write-Host "  python run_experiment.py --test      # Full hardware test"
Write-Host ""
Write-Host "NOTE: Camera needs light to capture frames" -ForegroundColor Yellow
Write-Host "      Make sure laser is on and aligned!" -ForegroundColor Yellow
Write-Host ""
