# GigE Camera Setup Guide
# Xenics Bobcat 320 GigE via Ethernet-to-USB Adapter

## Overview

The Xenics Bobcat 320 GigE uses **Gigabit Ethernet (GigE Vision)** protocol instead of USB. This is connected to your computer via an **Ethernet-to-USB adapter**.

GigE cameras are great for high bandwidth but require network configuration.

---

## Initial Setup (Do This Once)

### 0. Fix Xeneth SDK DLL Issue (If Camera Not Detected)

⚠️ **If you get DLL errors**, see **[XENETH_SDK_FIX.md](XENETH_SDK_FIX.md)** first!

Quick fix: Add `C:\Program Files\Xeneth` to your system PATH, then restart terminal.

### 1. Install Xeneth Software

Download and install Xeneth SDK from Xenics:
- Includes GigE Vision drivers
- Provides camera configuration tools
- Contains Python bindings

After installation:
```powershell
# Install Python bindings
pip install "C:\Program Files\Xeneth\Sdk\Python\xenics-*.whl"
```

### 2. Configure Network Adapter

**Important:** The Ethernet-to-USB adapter needs a static IP in the same subnet as the camera.

#### Step-by-Step:

1. **Find the adapter:**
   - Open Control Panel → Network and Sharing Center
   - Click "Change adapter settings"
   - Identify the Ethernet adapter (connected to camera)
   - Usually named "Ethernet 2" or similar

2. **Set static IP:**
   - Right-click adapter → Properties
   - Select "Internet Protocol Version 4 (TCP/IPv4)"
   - Click "Properties"
   - Select "Use the following IP address"
   - Set:
     - IP address: `192.168.1.100`
     - Subnet mask: `255.255.255.0`
     - Default gateway: (leave blank)
   - Click OK

3. **Verify camera IP:**
   - Open Xeneth software
   - Go to Camera → Discover
   - Note the camera IP address (usually `192.168.1.1` or similar)
   - Ensure it's in the same subnet (192.168.1.x)

4. **Optional Performance Tweaks:**
   - In adapter properties, click "Configure"
   - Go to "Advanced" tab
   - Set "Jumbo Packet" or "Jumbo Frame" to **9014 bytes** (if available)
   - This improves GigE performance

### 3. Firewall Settings

Windows Firewall may block GigE Vision traffic:

1. Open Windows Defender Firewall
2. Click "Advanced settings"
3. Create **Inbound Rule:**
   - Rule Type: Program
   - Program: `C:\Program Files\Xeneth\bin\Xeneth.exe`
   - Action: Allow the connection
   - Apply to all profiles
   - Name: "Xeneth GigE Camera"

4. Or disable firewall for the camera's network adapter:
   - Network and Sharing Center → Change adapter settings
   - Right-click camera adapter → Properties
   - Uncheck "Microsoft Network Firewall Driver" (if safe to do so)

---

## Testing Camera Connection

### Method 1: Xeneth Software

1. Open Xeneth software
2. File → New Camera
3. Should auto-discover the Bobcat 320 GigE
4. If found, you'll see live preview
5. Test capturing an image

**If camera not found:**
- Check Ethernet cable is plugged in (to adapter)
- Verify adapter has link lights
- Verify IP addresses are in same subnet
- Try pinging camera: `ping 192.168.1.1` (or whatever camera IP is)

### Method 2: Python Discovery

```powershell
python -c "from XenicsCam import dev_discovery; dev_discovery()"
```

Expected output:
```
Device[0] Bobcat 320 GigE @ 192.168.1.1 (GigE)
PID: 0x1234
Serial: 14931
URL: gev://192.168.1.1
State: Available
```

If this works, copy the URL to your `experiment_config.yaml`:
```yaml
camera:
  url: "gev://192.168.1.1"  # Use discovered URL
```

### Method 3: Full Python Test

```python
import sys
sys.path.append(r'Code That Connects To Other Code\Code That Connects To Other Code')

from XenicsCam import xCam, dev_discovery

# Discover
url = dev_discovery()

# Connect
camera = xCam(url=url)

# Capture frame
frame = camera.getFrame()
print(f"Frame shape: {frame.shape}")
print(f"Frame dtype: {frame.dtype}")
print(f"Min: {frame.min()}, Max: {frame.max()}")

# Cleanup
camera.stopCapture()
camera.closeCamera()
```

---

## Common Issues

### "No devices found"

**Causes:**
- Camera not powered
- Ethernet cable unplugged
- Network adapter not configured
- Wrong subnet

**Fix:**
1. Check physical connections (cable, power)
2. Verify adapter IP: `ipconfig` and look for your adapter
3. Ping camera: `ping 192.168.1.1`
4. Open Xeneth software - if it finds camera, Python should too
5. Try different camera IP if you changed it

### "Device busy" or "State: Busy"

**Cause:** Another program has the camera open (Xeneth software, previous Python script)

**Fix:**
1. Close Xeneth software
2. Close all Python processes
3. Restart the Python script
4. If still busy, reboot computer or power cycle camera

### Slow frame rates / dropped frames

**Cause:** Network bandwidth limitations with Ethernet-to-USB adapter

**Fixes:**
1. Enable Jumbo Frames on network adapter (9014 bytes)
2. Use USB 3.0 port for the adapter (not USB 2.0)
3. Close other network-intensive applications
4. In Xeneth, reduce ROI (region of interest) if possible
5. Consider dedicated GigE network card if sustained high speed needed

### Images look wrong / corrupt

**Cause:** Packet loss on network

**Fix:**
1. Check Ethernet cable quality
2. Enable Jumbo Frames
3. Reduce exposure time temporarily
4. Update network adapter drivers
5. Try different USB port

---

## Network Configuration Reference

### Recommended Settings

| Setting | Value |
|---------|-------|
| Adapter IP | 192.168.1.100 |
| Subnet Mask | 255.255.255.0 |
| Camera IP | 192.168.1.1 (check in Xeneth) |
| MTU / Jumbo Frames | 9014 bytes |
| Speed/Duplex | Auto-Negotiate or 1 Gbps Full |

### Changing Camera IP (if needed)

If you need to change the camera's IP address:

1. Open Xeneth software
2. Go to Tools → Device Manager
3. Select your camera
4. Set new IP address
5. Click Apply
6. Update your `experiment_config.yaml` with new URL

---

## Xeneth Software Calibration

The camera should have a calibration file loaded for best results:

**Current calibration:**
```
C:\Program Files\Xeneth\Calibrations\XC-(10-06-2021)-500us_14931.xca
```

This is loaded automatically by `XenicsCam.py` (line 80).

**If you need different calibration:**
1. Open Xeneth software with camera connected
2. Load desired calibration file
3. Test it works
4. Update the path in `experiment_config.yaml`:
   ```yaml
   camera:
     calibration_file: "C:\\Path\\To\\YourCalibration.xca"
   ```

---

## Performance Tips

### For Data Collection:

1. **Disable Windows power saving** on the network adapter:
   - Device Manager → Network adapters
   - Right-click your adapter → Properties
   - Power Management tab
   - Uncheck "Allow computer to turn off this device"

2. **Close bandwidth-heavy apps:**
   - Streaming, large downloads, cloud sync
   - Other camera software

3. **Use quality Ethernet-to-USB adapter:**
   - USB 3.0 or higher
   - Gigabit Ethernet support
   - Known brand (Anker, TP-Link, etc.)

### For Processing:

GigE connection doesn't affect processing, only data collection.

---

## Quick Diagnostic

Run this to check everything:

```powershell
# Check network config
ipconfig

# Look for your adapter (192.168.1.100)
# Should show:
#   Ethernet adapter Ethernet X:
#     IPv4 Address: 192.168.1.100
#     Subnet Mask: 255.255.255.0

# Ping camera
ping 192.168.1.1

# Should get replies if camera is reachable

# Python discovery
python -c "from XenicsCam import dev_discovery; dev_discovery()"

# Should list camera
```

---

## Still Having Issues?

1. **Try Xeneth software first** - if it can't connect, Python won't either
2. **Check Event Viewer** (Windows) for network adapter errors
3. **Update drivers** for Ethernet-to-USB adapter
4. **Try different USB port** (must be USB 3.0 for best performance)
5. **Power cycle camera** (if it has external power)
6. **Reboot computer** (clears stuck network states)

---

## Contact Support

If all else fails:
- **Xenics Support:** support@xenics.com
- **Documentation:** Check Xeneth SDK documentation
- **Lab Members:** Ask Caleb or Rumana who have used this camera before

---

## Notes

- GigE cameras are robust once configured but can be finicky initially
- The Ethernet-to-USB adapter adds another layer of potential issues
- If possible, direct Ethernet connection (without USB adapter) is more reliable
- Consider a dedicated GigE network card if you do lots of imaging

Good luck! 🎥
