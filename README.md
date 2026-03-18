# Photonic Lantern Digital Holography Automation

Automated data collection and processing pipeline for the digital holography testbed at UCF CREOL.

**Author:** Amarnath  
**Lab:** Stephen Eikenberry's Group, CREOL  
**Date:** March 2026

---

## Overview

This project automates the entire workflow for characterizing photonic lanterns using digital holography:

1. **Data Collection**: Automatically cycles through photonic lantern legs and wavelengths, captures interference patterns, and adjusts polarization to maximize fringe visibility
2. **Data Processing**: Processes hologram images via FFT, extracts twin images, performs mode decomposition, and generates analysis plots

---

## Hardware Setup

The testbed consists of:

- **HP 8168E Tunable Laser Source** (1475-1575 nm)
- **Dicon GP700 Fiber Optic Switch** (selects photonic lantern legs)
- **Thorlabs Motorized Polarization Controller** (3 paddles)
- **Xenics InGaAs Camera** (Bobcat 320 GigE)
- **Photonic Lantern** under test
- **Optical interferometer** setup (reference + signal beams)

### Physical Connections

Before running, ensure:
- ✓ Laser connected via GPIB (check address in config)
- ✓ Fiber switch connected via RS-232 serial (default COM6)
- ✓ Polarization motors connected via USB (serial number in config)
- ✓ Camera connected via Ethernet-to-USB adapter and Xeneth drivers installed
  - Camera uses GigE Vision protocol (Gigabit Ethernet)
  - May need to configure network adapter settings (see troubleshooting)
- ✓ Reference beam polarization manually adjusted with fixed paddles
- ✓ Safety: Laser power set to safe level (~200 µW)

---

## Installation

### Prerequisites

1. **Python 3.8+**

2. **Install Xeneth SDK** (for camera control):
   ```powershell
   # Xeneth should already be installed if you have Caleb's code working
   # The Python bindings are already included in the project (from Caleb's copy)
   
   # If camera isn't detected, see XENETH_SDK_FIX.md for DLL troubleshooting
   # You may need to add C:\Program Files\Xeneth to your system PATH
   ```

3. **Install Thorlabs Kinesis** (for motors):
   - Download and install from Thorlabs website
   - Ensure DLLs are in `C:\Program Files\Thorlabs\Kinesis\`

4. **Python packages**:
   ```powershell
   pip install numpy scipy matplotlib pyyaml
   pip install pyserial pyvisa pyvisa-py
   pip install opencv-python pillow
   ```

---

## Configuration

Edit `experiment_config.yaml` to match your setup:

### Key Settings

```yaml
hardware:
  laser:
    gpib_address: "GPIB0::24::INSTR"  # Check with NI-VISA
    power_uw: 208
  
  camera:
    url: "cam://0?fg=none"  # Auto-detect or specify
    calibration_file: "C:\\Path\\To\\Calibration.xca"
  
  fiber_switch:
    port: "COM6"  # Check in Device Manager
  
  polarization_motors:
    serial_number: "38394984"  # Check Kinesis software

experiment:
  legs: [1, 2, 3, 4, 5, 6, 7]  # Lantern output ports to test
  wavelengths: [1540, 1545, 1550, 1555, 1560]  # nm
  
  fringe_detection:
    enabled: true
    min_visibility: 0.15
    max_attempts: 5  # Polarization optimization tries
```

---

## Usage

### Quick Start

```powershell
# 1. Test hardware connections
python run_experiment.py --test

# 2. Run data collection
python run_experiment.py --collect

# 3. Process the collected data
python run_experiment.py --process

# 4. Or run everything at once
python run_experiment.py --collect --process
```

### Advanced Usage

```powershell
# Use custom config file
python run_experiment.py --config my_config.yaml --collect

# Process with live plot display
python run_experiment.py --process --show-plots

# Run collection only (process later)
python run_experiment.py --collect

# Process existing data from previous session
python run_experiment.py --process
```

---

## Output Files

### Data Collection Output

```
holography_data/
├── session_summary.yaml              # Metadata for entire session
├── leg01-wavelength1540.npy          # Hologram images
├── leg01-wavelength1540.yaml         # Per-image metadata
├── leg01-wavelength1545.npy
├── leg01-wavelength1545.yaml
└── ...
```

### Processing Output

```
holography_data/processed_results/
├── processing_summary.yaml           # Overall results summary
├── leg01-wavelength1540_results.npz  # Numerical results (mode decomp, etc.)
├── leg01-wavelength1540_analysis.png # Visualization plots
├── leg01-wavelength1545_results.npz
├── leg01-wavelength1545_analysis.png
└── ...
```

---

## File Descriptions

### Core Pipeline Files

| File | Description |
|------|-------------|
| `run_experiment.py` | **Main entry point** - runs collection and/or processing |
| `data_collection.py` | Automated data acquisition pipeline |
| `data_processing.py` | Hologram processing and mode decomposition |
| `fringe_detection.py` | Algorithms for detecting interference fringes |
| `experiment_config.yaml` | Configuration parameters |

### Hardware Drivers

| File | Description |
|------|-------------|
| `Code That Connects To Other Code/`<br>`  D700DiconSwitch.py` | Dicon fiber switch driver |
| `  HPTunableLaserSource.py` | HP laser control |
| `  XenicsCam.py` | Xenics camera interface |
| `  polMotors.py` | Polarization motor controller |

### Processing Utilities

| File | Description |
|------|-------------|
| `HolographyTutorial-master/`<br>`  calebsUsefulFunctions.py` | FFT, mode decomp, plotting |
| `  MMF.py` | LP mode generation |
| `Caleb Mode Playground/`<br>`  usefulFunctions.py` | Additional analysis tools |

---

## Workflow Details

### Data Collection Workflow

```
┌─────────────────────────────────────────┐
│ 1. Connect Hardware                     │
│    - Laser, Camera, Switch, Motors      │
└─────────────────────┬───────────────────┘
                      │
┌─────────────────────▼───────────────────┐
│ 2. For each photonic lantern leg:       │
│    - Switch fiber to leg N              │
│    - Wait for settling                  │
└─────────────────────┬───────────────────┘
                      │
┌─────────────────────▼───────────────────┐
│ 3. For each wavelength:                 │
│    - Set laser wavelength               │
│    - Capture camera frame               │
└─────────────────────┬───────────────────┘
                      │
┌─────────────────────▼───────────────────┐
│ 4. Check fringe visibility              │
│    - Calculate fringe metric            │
│    - If poor: optimize polarization     │
│    - Re-capture frame                   │
└─────────────────────┬───────────────────┘
                      │
┌─────────────────────▼───────────────────┐
│ 5. Save data                            │
│    - Save .npy image                    │
│    - Save .yaml metadata                │
└─────────────────────┬───────────────────┘
                      │
                  [Repeat]
```

### Data Processing Workflow

```
┌─────────────────────────────────────────┐
│ 1. Load hologram image                  │
└─────────────────────┬───────────────────┘
                      │
┌─────────────────────▼───────────────────┐
│ 2. Compute 2D FFT                       │
│    - DC component at center             │
│    - Twin images at symmetric positions │
└─────────────────────┬───────────────────┘
                      │
┌─────────────────────▼───────────────────┐
│ 3. Find twin image centroids            │
│    - Filter DC components               │
│    - Detect peaks in quadrants          │
└─────────────────────┬───────────────────┘
                      │
┌─────────────────────▼───────────────────┐
│ 4. Extract and crop twin image          │
│    - Isolate one twin image             │
│    - Apply Butterworth filter           │
└─────────────────────┬───────────────────┘
                      │
┌─────────────────────▼───────────────────┐
│ 5. Inverse FFT to recover field         │
│    - Get complex electric field         │
│    - Apply quadratic phase correction   │
└─────────────────────┬───────────────────┘
                      │
┌─────────────────────▼───────────────────┐
│ 6. Mode decomposition                   │
│    - Project onto LP mode basis         │
│    - Calculate mode powers              │
│    - Reconstruct field                  │
│    - Calculate fidelity                 │
└─────────────────────┬───────────────────┘
                      │
┌─────────────────────▼───────────────────┐
│ 7. Save results and plots               │
│    - Mode decomposition coefficients    │
│    - Analysis visualizations            │
└─────────────────────────────────────────┘
```

---

## Troubleshooting

### Hardware Issues

**Laser not connecting:**
- Check GPIB address with NI-VISA software
- Ensure GPIB interface is properly connected
- Try power cycling the laser

**Camera not found:**
- Verify Xeneth SDK is installed
- Run camera discovery: `python -c "from XenicsCam import dev_discovery; dev_discovery()"`
- Check Ethernet-to-USB adapter connection
- **See [GIGE_CAMERA_SETUP.md](GIGE_CAMERA_SETUP.md) for detailed GigE camera configuration**
- **GigE Camera Network Setup:**
  - Open Network Adapter settings
  - Find the Ethernet adapter (connected to camera)
  - Set static IP address (e.g., 192.168.1.100)
  - Set subnet mask to 255.255.255.0
  - Camera default IP is usually 192.168.1.x (check Xeneth software)
  - Disable firewall for this adapter if needed
  - In Xeneth software, configure camera network settings
  - May need to increase "Jumbo Frames" MTU for better performance

**Fiber switch not responding:**
- Verify COM port in Device Manager (Windows)
- Check RS-232 cable connection
- Try manual test: `python -c "from D700DiconSwitch import D700DiconSwitch; s = D700DiconSwitch('COM6'); s.move_to_position(1, 2)"`

**Motors not moving:**
- Ensure Kinesis software can see the motors
- Check USB connection
- Verify serial number matches config

### Fringe Visibility Issues

**No fringes visible:**
- Check reference beam polarization (manual paddles)
- Ensure both beams are reaching camera
- Verify optical alignment
- Try increasing laser power (within safe limits)
- Try manual polarization adjustment

**Polarization auto-optimization not working:**
- Increase `max_attempts` in config
- Adjust `angle_step` (smaller = finer search)
- Try different `check_method` (variance or fft_peaks)
- Lower `min_visibility` threshold temporarily

### Processing Issues

**Mode decomposition poor fidelity:**
- Check if fringes were visible during acquisition
- Verify twin image centroid detection (check plots)
- Adjust phase correction parameters
- Ensure mode parameters match fiber specs

**Import errors:**
- Ensure all paths in sys.path are correct
- Check that MMF.py and usefulFunctions.py are accessible
- Verify all dependencies installed

---

## Theory Background

### Digital Holography

The interferometer creates interference between:
- **Reference beam**: Known, stable beam
- **Signal beam**: Light from photonic lantern output

The interference pattern (hologram) is captured by the camera. The FFT of this hologram produces:
- **DC component**: Overall intensity
- **Twin images**: Contain field amplitude and phase information

### Mode Decomposition

The recovered electric field is decomposed into LP (linearly polarized) modes:

$$E_{total} = \sum_{i} c_i E_i^{LP}$$

where $c_i$ are complex coefficients representing mode power and phase.

The **fidelity** metric measures how well the mode decomposition reconstructs the original field:

$$F = |\langle E_{recovered} | E_{reconstructed} \rangle|$$

---

## Tips for Best Results

1. **Start with test mode**: Always run `--test` before data collection
2. **Check alignment**: Use red light checker first (ask lab members)
3. **Optimize one leg manually**: Find good polarization settings as reference
4. **Save often**: Collection can take hours for full wavelength sweep
5. **Monitor first few acquisitions**: Check early images to verify quality
6. **Calibrate camera**: Load proper calibration file for your camera
7. **Document changes**: Use git to track config changes between sessions

---

## Future Improvements

- [ ] Add real-time preview during collection
- [ ] Implement gradient-based polarization optimization
- [ ] GPU acceleration for FFT processing
- [ ] Automated calibration of pixel size
- [ ] Web dashboard for monitoring experiments
- [ ] Machine learning for fringe quality assessment

---

## References

- Slides from Caleb: "Holography Workflow.pptx"
- Mode coupling equations: [Optics Letters 23, 986 (1998)](https://opg.optica.org/ol/fulltext.cfm?uri=ol-23-13-986)
- Dicon GP700 Manual: [Link](https://www.artisantg.com/info/Dicon_GP700_Manual.pdf)

---

## Contact

**Amarnath**  
Physics Student, UCF

**PI: Stephen S. Eikenberry**  
Professor, CREOL & Physics Department  
University of Central Florida

**Lab Members:**
- Caleb Dobias (PhD - graduating soon)
- Rumana Akhter (PhD - new student)
- Miguel Romer (previous work on testbed)

---

## License

This project is for research use at UCF CREOL. Please credit when using or modifying.

---

## Acknowledgments

Shoutout to Caleb for building the testbed and providing all the code snippets. Thanks to Steve for the opportunity and Miguel for the previous iteration work.

Now go collect some data! 🔬✨
