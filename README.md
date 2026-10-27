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
  the off-axis hologram. Frames are validated: clipping is flagged at any
  ceiling, including cameras that clip below full scale.
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

`holo/` is the library — every line of physics lives there. The desktop app and
the `holo` command are two front ends over it, and neither contains analysis
code of its own, so they can never drift apart.

```
holo/                          THE LIBRARY
  pipeline.py                  combines both engines — change processing here
  data_processing.py           single-frame reconstruction + LP decomposition
  multiport_reconstruction.py  cross-port (paper-fidelity) reconstruction + TM
  fringe_detection.py          fringe metric + polarization auto-optimizer
  discovery.py                 folder -> records; frame loading and staging
  config.py                    config loading
  runtime.py                   frozen-build paths + Xeneth DLL bootstrap
  cli.py                       the `holo` command
  lib/                         LP modes, FFT math, vendored Xeneth SDK
  hardware/                    drivers (laser, camera, switch, motors)

gui/                        PySide6 (Qt6) app — window, tabs, acquisition loop
main.py                     GUI launcher (thin entry point)
tools/                      build script + hardware probes
tests/                      golden-file + unit tests (`uv run pytest`)
experiment_config.yaml      instrument addresses + sweep parameters
docs/                       setup guides (GigE camera, Xeneth SDK)
```

## Command line

```sh
holo acquire -o ./run            # sweep 1530-1560 nm, 3 exposures per point
holo process ./data              # reconstruct a folder (up to 8 processes)
holo tm ./data -o tm.npz         # reconstruct + export the transfer matrix
holo doctor                      # check the install, config and instruments
holo probe switch                # talk to one instrument
holo gui                         # launch the desktop app
```

`uv run holo <command>`, or `python -m holo` without installing. Every command
takes `--help`. `process.py` still works as a deprecated shim for
`holo process`.

### Acquiring a sweep by hand

`holo acquire` drives only the laser and the camera — you connect the lantern
leg and set the paddles yourself, which is the usual way to take a single-leg
test. Everything is a flag; no config file to edit.

```sh
holo acquire --start 1530 --stop 1560 --step 1 -n 3 --leg 1 -o ./run
holo acquire --start 1530 --stop 1560 -n 3 --dry-run   # print the plan, no hardware
```

`-n 3` takes three exposures back to back at each wavelength and writes them to
`run/rep01`, `run/rep02`, `run/rep03`. They are separate folders on purpose:
frame discovery keeps one file per (leg, wavelength), so repeats sharing a
folder would leave all but one silently unprocessed. Each `repNN` is a complete
sweep — reconstruct one with `holo process ./run/rep01`.

Every frame gets a `.png` preview and a `.yaml` sidecar recording the commanded
*and* measured wavelength (the HP 8168E queues errors instead of raising, so a
rejected tune otherwise looks like a good frame at the wrong λ). Saturated
frames are flagged and the command exits non-zero — clipping makes intensity
nonlinear in the field, so both amplitude and phase are wrong.

Using it as a library:

```python
from holo import HolographyDataProcessor, pipeline, discovery

records, cache = discovery.stage("./data", default_wl=1550)
rows = pipeline.process_records(HolographyDataProcessor(), records, config=cfg)
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

All fidelities below use the 8-mode basis unless stated otherwise, and each
says how many frames it covers.

| data | frames | fidelity | notes |
|---|---|---|---|
| Jun 9 2026 sweep, port 1, 1525–1575 nm | 51 | **97.2 ± 0.5%**, worst 95.8% | background-subtracted |
| Aug 4 2026 7-port sweep (Rumana Akhter), 1525–1569 nm | 215 of 315 | **92.7 ± 1.7%**, worst 83.9% | 100 frames clip at 45000 counts and are excluded |
| Caleb's 19-port archive, multiport, 23 modes | 969 | 96.68 ± 1.58%, worst 80.0% | reproduces his own saved run (96.89%) |
| committed test frame | 1 | 0.9776 (8 modes), 0.9788 (15 modes) | `GOLDEN_FIDELITY` |

- **Speed:** Caleb's 969 frames run in 65 s through the paper's pipeline with
  8 processes (5.3 min serial). The 315-frame 7-port sweep runs in 57 s
  through both engines. Every speedup was checked to give identical output.
- **Outside check:** a near-lossless lantern sends different ports to
  orthogonal fields. On the 7-port sweep, different ports' fields overlap
  0.113 on average (978 pairs), and the same port 1 nm apart overlaps 0.992.
  This is necessary, not sufficient.
- **Multiport on this rig's data** gives 68.9% on the 215 unclipped 7-port
  frames, below single-frame. The cause is the shared basis centre. Each
  port's light sits 9–16 px off it in a different direction, and forcing one
  centre costs 12.5 points. The single-frame engine re-centres each frame,
  which hides this. So an 8-mode basis around one axis does not fully describe
  this lantern. Its core size will decide whether it needs more modes. Until
  then, `pipeline` keeps the better engine per frame.
- **The library also trails on a single port.** On the one-port Jun 9 sweep
  (51 frames, no background subtraction) it reaches 85.0%, against 96.6% for
  single-frame. With one port there is no per-port centring, so this
  ~11-point gap is a separate open problem. Filter settings, crop centre and
  carrier method have been ruled out.
- **Mode count is unconfirmed.** Doubling the basis from 8 to 15–17 modes
  raises the Jun 9 fidelity only from 97.2% to 97.7%. Extra modes mostly fit
  noise. See CLAUDE.md, "Two open physics questions."
- **Multiport is a verified reproduction of Caleb's analysis.**
  - Carrier centroids match to 0.000 px.
  - The interpolated twin image matches (\|overlap\| = 1.000000).
  - Mode decompositions match at 0.997–0.9998 cosine similarity.
  - The paper's printed 98% ± 0.8% is not reproducible from that dataset,
    here or by Caleb's own saved run (96.9%). Tuning the Butterworth passband
    to reach 98% deletes real field content, which is a false fix.
  - Pinned by `tests/test_multiport.py`. It skips unless the gitignored
    dataset is unpacked to `_caleb_ref/`.
- The DiCon GP700 switch is being replaced, and its driver may need updating
  for the new unit.

## Credits

Amarnath Patel (UCF Physics / CREOL, Eikenberry group), building on Caleb
Dobias's original measurement and analysis work (see the paper above). The
Aug 4 2026 7-port sweep was taken by Rumana Akhter with this software.
