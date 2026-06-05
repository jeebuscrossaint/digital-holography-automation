# Photonic Lantern Digital Holography Automation

Automated measurement and analysis of the **wavelength-dependent transfer
matrix of a photonic lantern** by off-axis digital holography — for Prof.
Stephen Eikenberry's group at UCF CREOL.

A photonic lantern maps several single-mode fibers to the guided modes of a
multimode fiber; that mapping is a complex-valued *transfer matrix* that
evolves with wavelength. This software automates measurement of the encoding
matrix: it sweeps the input port and wavelength, captures an off-axis hologram
of the multimode output at each point, and recovers the complex field
(amplitude **and** phase) for decomposition into LP modes — one row of the
transfer matrix per measurement.

The reconstruction follows the method in:

> C. Dobias, M. A. Römer, S. Bhargava, *et al.*, "Wavelength-dependent
> evolution of full-field transfer matrices in photonic lanterns,"
> *Optics Express* **34**(9), 17217 (2026).
> https://doi.org/10.1364/OE.595908

---

## What it does

- **Acquire** — for each lantern port (fiber switch) × wavelength (tunable
  laser), auto-optimize polarization for maximum fringe contrast, then capture
  the off-axis hologram. Frames are validated (saturation/clipping is rejected).
- **Reconstruct** — FFT the hologram → isolate the off-axis sideband →
  demodulate to baseband → Butterworth low-pass → inverse FFT to the complex
  field; optimize mode-field diameter, quadratic-phase correction, and position
  for best fidelity; decompose into LP modes.
- **Run unattended** — the goal is a full 1525–1575 nm × all-ports sweep with
  only a couple of minutes of human time: line it up, hit start, walk away.

## Hardware

| Component | Model | Interface |
|---|---|---|
| Tunable laser | HP/Agilent 8168E (1475–1575 nm) | GPIB · Keysight VISA |
| Camera | Xenics Bobcat 320 GigE (InGaAs, 320×256) | GigE Vision |
| Fiber switch | DiCon GP700 | RS-232 |
| Polarization | Thorlabs MPC320 (3 paddles) | USB · Kinesis |

## Quick start

The shipping app is a **single native Windows executable** — no Python, Node,
server, or browser needed on the lab machine:

```sh
uv run python tools/build_app.py      # -> dist/Digital Holography.exe
```

Copy `dist/Digital Holography.exe` to the lab PC and double-click. **Connect
All → Start Experiment.** Config, logs, and data are written next to the .exe.

Run from source instead (needs [uv](https://docs.astral.sh/uv/); no Node):

```sh
uv sync
./start.bat            # = uv run python main.py
```

One-time per machine: install Keysight IO Libraries + Xenics Xeneth SDK and run
the camera firewall rule — see **[LAB_SETUP.md](LAB_SETUP.md)**.

## Repository layout

```
main.py                tkinter GUI — the app (acquisition + processing)
data_processing.py     hologram reconstruction + LP-mode decomposition
fringe_detection.py    fringe metric + polarization auto-optimizer
hardware/              instrument drivers (laser, camera, switch, motors)
lib/                   LP-mode generation + FFT helpers (MMF, Caleb's funcs)
tools/                 build scripts (build_app.py) + hardware probes
experiment_config.yaml instrument addresses + sweep parameters
docs/                  setup guides (GigE camera, Xeneth SDK)
```

## Status & known limits

- Camera streaming, laser, motors, acquisition, the fringe auto-optimizer, and
  saturation rejection all work.
- Reconstruction reaches **~92% fidelity**; closing the gap to the paper's ~98%
  needs the exact imaging scale (µm/pixel) and a sub-pixel (Fourier
  fine-binning) centering pass.
- The DiCon GP700 switch is being replaced — its driver may need updating for
  the new unit.

## Credits

Amarnath Patel (UCF Physics / CREOL, Eikenberry group), building on Caleb
Dobias's original measurement and analysis work (see the paper above). Intended
for ongoing use by Rumana Akhter.
