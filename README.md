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
main.py                     app launcher (thin entry point)
gui/                        PySide6 (Qt6) app — window, tabs, acquisition loop
pipeline.py                 processing pipeline shared by the GUI and the CLI
process.py                  headless CLI: point it at any folder of holograms
data_processing.py          single-frame reconstruction + LP-mode decomposition
multiport_reconstruction.py cross-port (paper-fidelity) reconstruction + TM
fringe_detection.py         fringe metric + polarization auto-optimizer
hardware/                   instrument drivers (laser, camera, switch, motors)
lib/                        LP-mode generation + FFT helpers (MMF, Caleb's funcs)
tools/                      build script + hardware probes
tests/                      golden-file + unit tests (`uv run pytest`)
experiment_config.yaml      instrument addresses + sweep parameters
docs/                       setup guides (GigE camera, Xeneth SDK)
```

See **[CLAUDE.md](CLAUDE.md)** for how the two reconstruction engines relate and
where the physics lives.

## Reconstruction

Two engines, picked automatically by how much data the sweep has:

| | single-frame | multiport |
|---|---|---|
| module | `data_processing.py` | `multiport_reconstruction.py` |
| needs | one hologram | **≥ 2 legs** across the sweep |
| carrier | per-frame sub-pixel centroid, demodulated to baseband | centroid averaged over **all ports** per λ, then linear-fit vs λ, then Fourier Fine-Binning |
| basis | per-frame optimum | optima consolidated across the sweep (paper Sec. 2) |

Both compute the paper's fidelity η = \|⟨E_rec, E_S⟩ / (‖E_rec‖‖E_S‖)\|² (Eq. 5).
A multi-leg dataset runs both and keeps, per frame, whichever scored higher — so
the result can never be worse than single-frame.

## Status & known limits

- Camera streaming, laser, motors, acquisition, the fringe auto-optimizer, and
  saturation rejection all work.
- Single-frame reconstruction reaches **~97%** on the committed test frame.
  Pixel scale, mode-field diameter, field position, and the defocus
  quadratic-phase are *optimized numerically* (matching the paper — they are not
  measured on the bench).
- **That number is not directly comparable to the paper's 98%.** The paper
  measures a 19-port lantern with a 23-mode basis; this config uses a 15-mode
  basis on what the multiport path treats as a 7-port (8-mode) lantern. An
  oversized basis inflates fidelity by absorbing noise — see **CLAUDE.md,
  "Known physics discrepancy"**. Resolve the lantern's real mode count before
  quoting a fidelity against the paper.
- **Multiport is close to, but does not yet match, the paper.** Run over the
  paper's own archived dataset (19 ports × 51 wavelengths, 23-mode basis,
  consolidated basis, Caleb's own parameters) it gives **96.76% ± 0.95%** against
  the paper's 98% ± 0.8% — about 1.2 points unexplained. The fiber spec is not
  the cause. See **CLAUDE.md, "The missing 1.2 points"**, which also records why
  narrowing the Butterworth passband to reach 98% is a false fix. Pinned by
  `tests/test_multiport.py` (auto-skips without the dataset, gitignored/multi-GB).
- Multiport has **not** yet been validated on a leg × wavelength sweep from
  *this* rig — only on the paper's data. On the rig data available today it
  underperforms and the pipeline falls back to single-frame per frame.
- The DiCon GP700 switch is being replaced — its driver may need updating for
  the new unit.

## Credits

Amarnath Patel (UCF Physics / CREOL, Eikenberry group), building on Caleb
Dobias's original measurement and analysis work (see the paper above). Intended
for ongoing use by Rumana Akhter.
