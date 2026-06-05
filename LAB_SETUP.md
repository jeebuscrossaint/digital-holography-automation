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

This adds the inbound rule for the venv Python (tkinter app + Tauri dev)
and, if a release build is present, for the bundled sidecar `.exe`.

> If the camera *still* shows "No signal": make sure **Xeneth is fully
> closed** (only one program can hold the single GigE stream channel at a
> time), and confirm the camera shows a live image in Xeneth first.

---

## Running

### Native desktop app — the deliverable (single .exe, recommended)

The shipping app is the tkinter GUI packaged as **one native Windows
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

### Running from source (tkinter)

If you have the repo + venv, you can run the same GUI without packaging — needs
`uv` but no Node/Rust:

```sh
git clone <repo-url>
cd digital-holography-automation
# one time: install uv + the two SDKs above + run the firewall script
.\start.bat        # = uv run python main.py
```

Hit **Connect All**, then **Start Experiment**.

### The web app — recommended for the headless NUC (remote over Tailscale)

The control UI is also a normal web app: a FastAPI server (`server/main.py`)
serves both the UI and the hardware API on one port. Run it on the NUC and
drive the rig from your laptop/phone browser over Tailscale — no desktop
session needed, and **the experiment keeps running after you close the browser
or disconnect** (it runs in a background thread on the server).

```sh
# on the NUC (needs uv + the two SDKs + the firewall rule, same as above):
.\start-server.bat            # builds the UI once, serves on 0.0.0.0:8000
```

Then from any device on your tailnet open `http://<nuc-tailscale-name>:8000`.
(First run builds the UI, which needs Node; after that it's Python-only.)

To auto-start on boot, register `start-server.bat` as a Windows Task Scheduler
task ("run whether logged on or not") or wrap it with NSSM as a service.

> Security: only expose this over **Tailscale** (a private mesh of *your*
> devices) — never forward the port to the public internet; it's direct
> hardware control.

### From source (development)

For UI development with hot-reload, run the backend and the Vite dev server
separately (Vite proxies `/rpc` to the backend):

```sh
uv run uvicorn server.main:app --port 8000     # terminal 1 (API)
cd app && npm run dev                            # terminal 2 (UI @ :1420)
```

### Tauri desktop shell (optional)

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
