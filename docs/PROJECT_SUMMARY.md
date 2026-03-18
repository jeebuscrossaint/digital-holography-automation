# Project Summary - Digital Holography Automation

## What I Built For You

I've created a complete automation pipeline for your photonic lantern digital holography testbed. Here's what you got:

---

## 📁 Files Created

### Main Pipeline Files
1. **`run_experiment.py`** - Main entry point
   - Run data collection and/or processing
   - Test hardware connections
   - Command-line interface with options

2. **`data_collection.py`** - Automated data acquisition
   - Connects to all hardware (laser, camera, switch, motors)
   - Loops through legs and wavelengths
   - Auto-detects and optimizes fringe visibility
   - Saves hologram images + metadata

3. **`data_processing.py`** - Hologram analysis
   - FFT computation
   - Twin image extraction
   - Mode decomposition into LP modes
   - Generates visualization plots
   - Saves numerical results

4. **`fringe_detection.py`** - Fringe visibility algorithms
   - Multiple detection methods (variance, Michelson, FFT)
   - Automatic polarization optimization
   - Configurable thresholds

5. **`test_components.py`** - Individual hardware testing
   - Test each component separately
   - Debugging tool
   - Example code for manual control

### Configuration & Documentation
6. **`experiment_config.yaml`** - Central configuration
   - Hardware settings (ports, addresses, serial numbers)
   - Experiment parameters (legs, wavelengths, wait times)
   - Processing settings (modes, pixel size, etc.)
   - All in one place - easy to edit

7. **`README.md`** - Complete documentation
   - Overview of system
   - Installation instructions
   - Usage guide
   - Troubleshooting
   - Theory background
   - ~500 lines of detailed docs

8. **`QUICKSTART.md`** - Quick reference guide
   - Daily usage cheat sheet
   - Common commands
   - What to watch for during collection
   - Emergency procedures

9. **`requirements.txt`** - Python dependencies
   - All required packages
   - Installation instructions

10. **`.gitignore`** - Updated git ignore rules
    - Excludes data files (can be huge)
    - Keeps code and configs

### Hardware Driver Updates
11. **`D700DiconSwitch.py`** - Completed fiber switch driver
    - Was incomplete skeleton code
    - Now full-featured class with:
      - Connection management
      - Position switching
      - Query current state
      - Error handling

---

## 🔧 What Each Part Does

### Data Collection Workflow
```
Hardware Test → For Each Leg → For Each Wavelength →
Check Fringes → Optimize Polarization (if needed) →
Capture Image → Save .npy + .yaml → Repeat
```

**Features:**
- ✅ Fully automated loop through all legs × wavelengths
- ✅ Real-time fringe visibility detection
- ✅ Automatic polarization optimization
- ✅ Progress tracking and logging
- ✅ Safe shutdown on Ctrl+C
- ✅ Metadata saved with each image

### Data Processing Workflow
```
Load Hologram → FFT → Find Twin Images →
Extract Twin → IFFT to Recover Field →
Phase Correction → Mode Decomposition →
Calculate Fidelity → Generate Plots → Save Results
```

**Features:**
- ✅ Batch processes all collected images
- ✅ Generates comprehensive analysis plots
- ✅ Mode powers and decomposition coefficients
- ✅ Fidelity metrics for quality assessment
- ✅ Saves numerical results (.npz) and visualizations (.png)

---

## 🚀 How To Use

### Quick Start
```powershell
# 1. Test hardware
python run_experiment.py --test

# 2. Collect data
python run_experiment.py --collect

# 3. Process data
python run_experiment.py --process

# 4. Or do everything
python run_experiment.py --collect --process
```

### Testing Individual Components
```powershell
# Test just the laser
python test_components.py --laser

# Test just the camera
python test_components.py --camera

# Test everything
python test_components.py --all
```

---

## 📊 What You'll Get

### After Data Collection
```
holography_data/
├── session_summary.yaml            # Overall session info
├── leg01-wavelength1540.npy        # Raw hologram (NumPy array)
├── leg01-wavelength1540.yaml       # Metadata (wavelength, timestamp, fringes, etc.)
├── leg01-wavelength1545.npy
├── leg01-wavelength1545.yaml
└── ...
```

### After Processing
```
holography_data/processed_results/
├── processing_summary.yaml                  # Results summary
├── leg01-wavelength1540_results.npz         # Mode decomposition arrays
├── leg01-wavelength1540_analysis.png        # 4x3 plot grid with:
│                                            #   - Original hologram
│                                            #   - FFT spectrum
│                                            #   - Twin image locations
│                                            #   - Recovered field (amplitude, phase)
│                                            #   - Reconstructed field
│                                            #   - Mode power distribution
│                                            #   - LP mode basis functions
└── ...
```

---

## 🎯 Key Features

### Smart Automation
- **Fringe Detection**: Automatically determines if fringes are visible
- **Polarization Optimization**: Adjusts motors to maximize fringe contrast
- **Error Recovery**: Handles hardware glitches gracefully
- **Progress Tracking**: Real-time feedback on what's happening

### Robust Hardware Control
- **All 4 hardware components** implemented:
  - HP Tunable Laser (wavelength control)
  - Dicon Fiber Switch (leg selection)
  - Thorlabs Motors (polarization adjustment)
  - Xenics Camera (image capture)
- **Connection management**: Automatic connect/disconnect
- **Safety features**: Laser shutdown on exit

### Comprehensive Processing
- **FFT-based holography**: Extracts amplitude + phase
- **Mode decomposition**: Projects onto LP mode basis
- **Quality metrics**: Fidelity, mode powers
- **Beautiful visualizations**: 12-panel analysis plots

### Flexible Configuration
- **Single config file**: All parameters in one YAML
- **No hardcoded values**: Easy to adapt to different setups
- **Documented settings**: Comments explain each parameter

---

## 🔍 What to Check Before Running

1. **Hardware Connections**
   - [ ] Laser connected (GPIB)
   - [ ] Camera connected (Ethernet-to-USB adapter)
     - [ ] Network adapter configured with static IP
     - [ ] Camera visible in Xeneth software
   - [ ] Fiber switch connected (RS-232)
   - [ ] Motors connected (USB)

2. **Software Installation**
   - [ ] Python 3.8+
   - [ ] Xeneth SDK installed
   - [ ] Thorlabs Kinesis installed
   - [ ] Python packages (`pip install -r requirements.txt`)

3. **Configuration**
   - [ ] Edit `experiment_config.yaml`
   - [ ] Set correct COM ports and GPIB address
   - [ ] Choose legs and wavelengths to test
   - [ ] Set data output directory

4. **Physical Setup**
   - [ ] Reference beam aligned
   - [ ] Test with red light checker
   - [ ] Manual polarization paddles adjusted
   - [ ] Both beams reaching camera

---

## 🐛 Debugging Tools

If something doesn't work:

1. **Test Individual Components**
   ```powershell
   python test_components.py --laser   # Just laser
   python test_components.py --camera  # Just camera
   python test_components.py --all     # Everything
   ```

2. **Check Logs**
   - Look at terminal output
   - Check `experiment_log.txt` if enabled

3. **Verify Config**
   - Double-check COM ports
   - Verify GPIB address
   - Check file paths (Windows backslashes!)

4. **Manual Control**
   - Use test_components.py examples
   - Import classes directly in Python
   - Step through hardware operations

---

## 📈 Expected Performance

### Data Collection
- **Time per image**: ~5-10 seconds
  - 1s leg switching
  - 0.5s wavelength change  
  - 0-5s polarization optimization
  - 0.5s capture + save
  
- **Full session**: 30-60 minutes
  - For 7 legs × 7 wavelengths = 49 images

### Data Processing
- **Time per image**: 5-15 seconds
  - FFT computation
  - Twin image extraction
  - Mode decomposition
  - Plot generation

- **Full dataset**: 5-15 minutes
  - For 49 images

---

## 🎓 What You Learned (or Can)

The code demonstrates:
- Object-oriented hardware control
- YAML configuration management
- NumPy array processing
- Fourier optics (FFT/IFFT)
- Mode decomposition algorithms
- Matplotlib visualization
- Error handling and logging
- Command-line interfaces (argparse)
- Git workflow (commits, ignores)

Feel free to read through the code - it's well-commented!

---

## 🚧 Future Improvements (If You Want)

- [ ] Real-time preview window during collection
- [ ] Machine learning for fringe quality prediction
- [ ] GPU acceleration (CuPy for FFT)
- [ ] Web dashboard for remote monitoring
- [ ] Automated phase calibration
- [ ] Temperature/environmental monitoring
- [ ] Multi-leg parallel processing
- [ ] Database storage for long-term data

---

## 💡 Tips

1. **Start Small**: Test with 1-2 legs and 3 wavelengths first
2. **Monitor Progress**: Watch the first few images closely
3. **Save Configs**: Use git to track config changes
4. **Document**: Take notes on what works well
5. **Backup Data**: Copy to external drive regularly
6. **Ask Questions**: Caleb, Rumana, and Steve can help

---

## 🙏 Credits

**Built by**: Amarnath (with AI pair programming)
**Based on**: Caleb Dobias's original testbed code
**Lab**: Stephen Eikenberry's group, UCF CREOL
**For**: Photonic lantern characterization research

---

## 📞 Help

- **For hardware issues**: See README.md troubleshooting
- **For code questions**: Read docstrings and comments
- **For theory questions**: Check references in README.md
- **For lab-specific stuff**: Ask Caleb or Rumana

---

**Now go collect some data!** 🔬✨

Remember: Run `--test` first, watch for errors, and don't be afraid to stop and debug if something looks wrong. The hardware won't break if you Ctrl+C out of a run.

Good luck with your measurements!
