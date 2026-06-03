# Lab Setup Guide

Quick path for a new lab machine. Two SDKs need to be installed
manually (because of Windows driver / registry requirements); the
rest is bundled in this repo.

---

## What's bundled in the repo

| Component | How | Action needed |
|-----------|-----|---------------|
| **Thorlabs Kinesis** (paddle motors) | DLLs in `vendor/thorlabs/` | none — works out of the box |
| **Python interpreter** | Bundled into the installer via PyInstaller | none — included in the `.msi` |
| **All Python deps** (pyvisa, numpy, scipy, Pillow, etc.) | Compiled into the sidecar binary | none |
| **App + GUI** | Native `Digital Holography.exe` | none |

## What still needs separate install (one time per lab machine)

These two ship with kernel-mode drivers / shared system components,
so we can't legally bundle them — but they're both free downloads:

### 1. Keysight IO Libraries Suite — *required for the laser*

The HP 8168E laser is on GPIB. The Keysight 82357B USB-to-GPIB
adapter needs Keysight's IO Libraries Suite installed (registers
the VISA dispatcher in `C:\Windows\System32\visa64.dll`, the USB
driver, etc.).

  1. Download: https://www.keysight.com/find/iosuite (~700 MB)
  2. Run installer; accept defaults
  3. Reboot
  4. Open Keysight Connection Expert → the laser should appear at
     `GPIB0::24::INSTR` with `READY` LED solid on the adapter
  5. Set "Keysight 64-bit VISA" as the primary VISA in Settings →
     VISA Conflict Manager → General VISA Settings

### 2. Xenics Xeneth SDK — *required for the camera*

The Xenics Bobcat 320 GigE camera communicates over GigE Vision —
that needs the Xenics filter driver and Xeneth runtime.

  1. Download Xeneth from xenics.com (account required, free)
  2. Install
  3. Plug in the camera (or the Ethernet-to-USB adapter)
  4. Open Xeneth (the GUI) once to confirm the camera shows up

---

## Running

### From source (development)

```sh
git clone <repo-url>
cd digital-holography-automation
# Install uv if you don't have it: https://docs.astral.sh/uv/getting-started/installation/
.\start-tauri.bat
```

`start-tauri.bat` runs `uv sync` to set up the Python env, then
launches `npm run tauri dev`. First run compiles Rust (~1 min).

### From the installer (lab members)

  1. Grab the latest `Digital Holography_*_x64-setup.exe` from the
     `app/src-tauri/target/release/bundle/nsis/` folder of the build
     machine (or wherever it's distributed)
  2. Double-click to install
  3. Launch from the Start menu

The installer drops:
  - `Digital Holography.exe` (main app)
  - `holography-sidecar.exe` (Python brain, bundled)
  - All Thorlabs Kinesis DLLs

The two SDKs from the section above (Keysight IO Libraries +
Xenics Xeneth) still need to be installed once on each lab machine.

---

## Building a release

On a machine with everything installed:

```sh
# 1. Bundle the Python sidecar into a single .exe
uv run python tools/build_sidecar.py
# → drops app/src-tauri/binaries/holography-sidecar-<triple>.exe

# 2. Build the Tauri app + installers
cd app
npm run tauri build
# → app/src-tauri/target/release/bundle/
#     nsis/   Digital Holography_<ver>_x64-setup.exe   ← share this
#     msi/    Digital Holography_<ver>_x64_en-US.msi
```

---

## Hardware checklist

  - [x] HP 8168E tunable laser on GPIB
  - [x] Keysight 82357B USB-to-GPIB adapter plugged in
  - [x] Dicon GP700 fiber switch — RS-232 over a USB-to-serial cable
        (FTDI / Prolific driver, usually auto-installed by Windows)
  - [x] Thorlabs MPC320 polarization controller — USB
  - [x] Xenics Bobcat 320 GigE camera — Ethernet, optionally through
        an Ethernet-to-USB adapter

Run the app; the **Instrument chain** strip at the top will show
green dots when each device is online.
