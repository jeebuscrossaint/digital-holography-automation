# Lab Setup Guide

Quick path for a new lab machine. Two SDKs need to be installed
manually (because of Windows driver / registry requirements); the
rest is bundled in this repo.

---

## What's bundled in the repo

| Component | How | Action needed |
|-----------|-----|---------------|
| **Thorlabs Kinesis** (paddle motors) | DLLs in `vendor/thorlabs/` | none — works out of the box |
| **Python interpreter** | Bundled into the `.exe` via PyInstaller | none — included in the executable |
| **All Python deps** (pyvisa, numpy, scipy, Pillow, etc.) | Compiled into the `.exe` | none |
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

### 3. Camera firewall rule — *required, or the camera "connects" but shows no image*

⚠️ **This is the single most important step, and the easiest to miss.**

The Bobcat 320 streams images as **inbound UDP** (GigE Vision / GVSP).
Windows Firewall blocks inbound UDP **per-executable**. The Xeneth
installer whitelists `Xeneth64.exe` — so the Xeneth GUI streams fine — but
**our Python is a different executable and is not whitelisted**, so its
frames get silently dropped. The app then says *"Camera Online"* (the
control channel works) while the preview stays dead / **"No signal."**
It is **not** a light, exposure, calibration, or driver problem.

Fix (run once per machine — it self-elevates to admin and is safe to
re-run):

```powershell
powershell -ExecutionPolicy Bypass -File tools\setup_lab_machine.ps1
```

This adds the inbound rule for the venv Python (running from source) and,
if a packaged build is present, for `dist/Digital Holography.exe`.

> If the camera *still* shows "No signal": make sure **Xeneth is fully
> closed** (only one program can hold the single GigE stream channel at a
> time), and confirm the camera shows a live image in Xeneth first.

---

## Running

### Native desktop app — the deliverable (single .exe, recommended)

The shipping app is the PySide6 (Qt6) GUI packaged as **one native Windows
executable** — no Python, Node, web server, or WebView2 on the target machine.

Build it (on a dev machine with the venv):
```sh
uv run python tools/build_app.py        # -> dist/Digital Holography.exe
```
Then copy `dist/Digital Holography.exe` to the lab machine and double-click it.
Editable data (experiment_config.yaml, session.log, holography_data/) is created
**next to the .exe**, so put it in its own folder. The two hardware SDKs
(Keysight IO Libraries + Xenics Xeneth) and the camera firewall rule
(`tools/setup_lab_machine.ps1`) still need to be set up once per machine.

### Running from source (Qt)

If you have the repo + venv, you can run the same GUI without packaging — needs
`uv` but no Node/Rust:

```sh
git clone <repo-url>
cd digital-holography-automation
# one time: install uv + the two SDKs above + run the firewall script
.\start.bat        # = uv run python main.py
```

Hit **Connect All**, then **Start Experiment**.

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
