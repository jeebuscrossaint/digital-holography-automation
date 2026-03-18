# Xeneth SDK DLL Issue & Workaround

## The Problem

The Xeneth Python SDK can't find the runtime DLLs (`xeneth64.dll`). This is required for camera communication.

## What Caleb Did (That Worked)

Caleb has working code in `Code That Connects To Other Code\Code That Connects To Other Code\`:
- `XenicsCam.py` - his working camera driver
- `XenicsPython\Xenics\xenics\` - copy of Xeneth Python module
  
His code worked because the Xeneth DLLs were accessible to Python somehow.

## Current Status

✅ **We're using Caleb's working code directly** - no need to reinstall anything  
❌ **The DLLs still need to be found by Python**

## Quick Fixes to Try

### Option 1: Add Xeneth to System PATH (Permanent)

1. Press `Win + X` → System
2. Click "Advanced system settings"
3. Click "Environment Variables"
4. Under "System variables", find "Path"
5. Click "Edit" → "New"
6. Add: `C:\Program Files\Xeneth`
7. Click OK on everything
8. **Restart PowerShell/Terminal** (important!)
9. Test: `python test_components.py --camera`

### Option 2: Just Use Caleb's Folder Directly

Run everything from Caleb's directory:

```powershell
cd "Code That Connects To Other Code\Code That Connects To Other Code"
python -c "from XenicsCam import xCam; print('Testing...'); cam = xCam()"
```

If this works, we know it's just a PATH issue.

### Option 3: Copy Missing DLLs (If Found)

If you can find where `xeneth64.dll` actually is:

```powershell
# Search for it
Get-ChildItem C:\ -Recurse -Filter xeneth64.dll -ErrorAction SilentlyContinue

# If found, copy to project
Copy-Item "path\to\xeneth64.dll" "C:\Users\amarnath\Programming\doohickeydinklecombobertothe12thfactorial\"
```

## Why This Happened

The Xeneth SDK has two parts:
1. **Python wrapper** (`xenics` module) - ✅ We have this (from Caleb)
2. **C/C++ Runtime DLLs** (`xeneth64.dll`) - ❌ Python can't find these

The DLLs need to be either:
- In system PATH
- In same directory as Python script
- In Windows system directories
- In current working directory

## How Caleb Probably Had It Working

Caleb likely had one of:
- Xeneth in his system PATH
- Xeneth GUI application installed which registered DLL paths
- DLLs copied to his working directory
- Updated his PATH in PyCharm/Spyder environment

## Testing If Xeneth Is Properly Installed

```powershell
# Try launching Xeneth GUI
& "C:\Program Files\Xeneth\Xeneth64.exe"
```

If the GUI opens and can detect your camera, Xeneth IS installed.

Then the issue is just Python not finding the DLLs.

## Nuclear Option: Run From Caleb's Directory

Until we fix the DLL path, you can just run everything from where it works:

```powershell
cd "Code That Connects To Other Code\Code That Connects To Other Code"

# Test camera
python -c "from XenicsCam import dev_discovery; dev_discovery()"

# Or run modified pipeline from there
```

Then update all scripts to use relative paths to Caleb's code.

## What We've Already Done

✅ Copied `xenics` module from Caleb's XenicsPython folder  
✅ Updated `data_collection.py` to use Caleb's paths  
✅ Updated `test_components.py` to use Caleb's paths  
✅ All automation pipeline code ready to go

**Just need the DLL path issue resolved!**

## Recommendation

1. **Try Option 1** (add to PATH) - most reliable long-term fix
2. **Restart terminal** after changing PATH
3. **Test with**: `python test_components.py --camera`
4. If still doesn't work, try running Xeneth64.exe first to see if camera is even detected

## Still Not Working?

Check if there's a separate Xeneth SDK Runtime installer that needs to be run, or contact Caleb/Rumana to ask how they got it working initially.

The Python code is ready - it's just a DLL loading issue now! 🎥
