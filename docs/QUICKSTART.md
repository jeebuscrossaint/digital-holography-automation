# QUICK START GUIDE
# Photonic Lantern Digital Holography Automation

## First Time Setup

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

2. **Xeneth SDK Setup:**
   - ✅ Python bindings already included (using Caleb's working code)
   - If camera not detected, see **[XENETH_SDK_FIX.md](XENETH_SDK_FIX.md)**
   - May need to add `C:\Program Files\Xeneth` to system PATH

3. Install Thorlabs Kinesis:
   - Download from Thorlabs website
   - Ensure DLLs are in C:\Program Files\Thorlabs\Kinesis\

4. Edit experiment_config.yaml:
   - Set correct COM ports and GPIB addresses
   - Adjust legs and wavelengths to test
   - Set data output directory

## Hardware Checklist

Before running, verify:
- [x] Laser powered on and connected (GPIB)
- [x] Camera Ethernet-to-USB adapter connected (GigE Vision)
- [x] Camera network configured (static IP on adapter)
- [x] Fiber switch serial cable connected (RS-232)
- [x] Polarization motors USB connected
- [x] Reference beam manually aligned
- [x] Test sample beam with red light checker

## Daily Usage

### Test Hardware (always do this first!)
```powershell
python run_experiment.py --test
```

This will:
- Connect to all hardware
- Verify communication
- Report any issues

### Collect Data
```powershell
python run_experiment.py --collect
```

What happens:
- Loops through each leg
- Sweeps wavelengths
- Automatically adjusts polarization for fringes
- Saves hologram images to holography_data/

Time estimate: ~30-60 minutes (depends on # of legs × wavelengths)

### Process Data
```powershell
python run_experiment.py --process
```

What happens:
- Loads all hologram images
- Computes FFT and finds twin images
- Mode decomposition into LP modes
- Generates analysis plots
- Saves results to holography_data/processed_results/

Time estimate: ~1-5 minutes per image

### Run Everything
```powershell
python run_experiment.py --collect --process
```

Runs collection, then immediately processes all data.

## Monitoring Progress

During collection, watch for:
```
[3/35] Leg 2, λ = 1550 nm
  Fringe check: variance = 0.234 (threshold=0.15)
  ✓ Fringes visible!
  💾 Saved: leg02-wavelength1550.npy
```

Good signs:
- ✓ Fringes visible!
- Fringe metric > threshold
- No errors from hardware

Warning signs:
- ⚠ Fringes not visible, adjusting polarization...
- ⚠ Could not achieve good fringes
- ✗ Failed to capture frame

If you see warnings repeatedly:
1. STOP (Ctrl+C)
2. Check optical alignment
3. Manually adjust reference polarization with fixed paddles
4. Verify both beams are reaching camera
5. Try adjusting laser power

## Interpreting Results

After processing, check:

1. **Fidelity**: How well modes reconstruct the field
   - Good: > 0.85
   - OK: 0.70 - 0.85
   - Poor: < 0.70

2. **Mode Powers**: Distribution across LP modes
   - Ideal single-mode: >90% in LP01
   - Multi-mode: Power distributed across several modes

3. **Analysis Plots**: Visual inspection
   - Clear fringes in original hologram
   - Distinct peaks in FFT (twin images)
   - Clean recovered field
   - Smooth mode power distribution

## Common Issues

**"Laser not connecting"**
→ Check GPIB address in config matches NI-VISA
→ Power cycle laser

**"Camera not found"**
→ **See GIGE_CAMERA_SETUP.md for complete guide**
→ Check Ethernet-to-USB adapter is connected
→ Verify network adapter has static IP (e.g., 192.168.1.100)
→ Open Xeneth software to verify camera is detected there first
→ Run: python -c "from XenicsCam import dev_discovery; dev_discovery()"
→ If still not found, check Windows firewall settings for the adapter

**"No fringes visible" for all images**
→ Check reference beam polarization (manual paddles)
→ Verify optical alignment with red light
→ Increase laser power (safely)

**"Low fidelity" after processing**
→ Re-check fringe visibility during collection
→ Adjust phase correction parameters in config
→ Verify mode parameters (core radius, NA) match your fiber

## Tips

- Start with just 1-2 legs and 3 wavelengths for testing
- Monitor the first few images closely
- If polarization optimization takes too long, increase angle_step
- Save intermediate results (code does this automatically)
- Document any changes to config in git commits

## Emergency Stop

Press Ctrl+C to safely abort during collection.
Hardware will automatically disconnect.

## Help

See full documentation in README.md

For questions, ask:
- Caleb (built the testbed)
- Rumana (current user)
- Steve (PI)

Good luck! 🚀
