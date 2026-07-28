# CLAUDE.md

Photonic-lantern digital holography for UCF CREOL (Eikenberry group). The job:
measure the **wavelength-dependent transfer matrix** of a photonic lantern by
off-axis digital holography, reproducing

> C. Dobias, M. A. Römer, S. Bhargava, *et al.*, "Wavelength-dependent evolution
> of full-field transfer matrices in photonic lanterns," *Opt. Express* **34**(9),
> 17217 (2026). doi:10.1364/OE.595908 · arXiv:2604.22091

**Read the paper before changing reconstruction code.** The code exists to
implement that physics; "it runs" is not the bar.

## The physics, in short

A lantern maps N single-mode fibers onto the N guided modes of a multimode
fiber. That map is a complex transfer matrix that evolves with wavelength. To
measure one column: illuminate one port, interfere the MMF output with a tilted
reference plane wave, record the off-axis hologram, and recover the complex
field.

Recovery (paper Sec. 2), and what implements each step:

| Step | Where |
|---|---|
| FFT the raw **intensity** — do *not* sqrt it | `data_processing._recover_field` |
| Locate the off-axis sideband (twin) sub-pixel | same; multiport does it far better |
| Demodulate to baseband, Butterworth low-pass | same |
| Inverse FFT → complex field `E_S` | same |
| Optimize field position, mode-field diameter, quadratic-phase k | `process_single_hologram` |
| Decompose onto LP modes: `C_k = ⟨E_S, Ψ_k⟩ / (‖E_S‖‖Ψ_k‖)` (Eq. 3) | `calebsUsefulFunctions.modeDecomp` |
| Fidelity `η = \|⟨E_rec, E_S⟩ / (‖E_rec‖‖E_S‖)\|²` (Eq. 5) | `overlap2FieldsV2`, squared |

Paper's result: **98% ± 0.8%**, 19 ports × 51 wavelengths (1525–1575 nm),
23-mode basis, 34 µm MMF core diameter.

**This repo does not fully reproduce that yet.** Multiport, run over the paper's
own archived dataset (`_caleb_ref/10-17-2023-Wavelengths`) with Caleb's own
parameters and the 23-mode basis, gets **96.76% ± 0.95%**. About **1.2 points
are unexplained** — see below. Pinned by
`tests/test_multiport.py::test_consolidated_basis_matches_measured_fidelity`,
which auto-skips when the dataset is absent.

## Two reconstruction engines

- **`data_processing.py`** — single-frame. All it can see is one hologram, so
  the carrier centroid comes from that frame alone. The only option for a
  single-leg dataset.
- **`multiport_reconstruction.py`** — the paper's cross-port method, needs ≥ 2
  legs. Its accuracy comes from information that only exists across a full
  sweep: the carrier is set by the optics and is *common to every port*, so
  averaging the sideband over all ports at each wavelength — then linear-fitting
  the centroid against wavelength — pins it far better than any single frame.
  Then Fourier Fine-Binning (`fourier_interp_2d`, Ransom 2002) resamples
  sub-pixel so demodulation leaves no residual phase ramp.

**`pipeline.py` is the only place that combines them.** It runs multiport once
over the sweep when ≥ 2 legs are present, then per frame keeps whichever engine
scored higher. Both the GUI's Process button and `process.py` call it — if you
change processing behavior, change it there, not in a front end. (These were
three drifted copies before; don't re-fork them.)

### Basis consistency — the non-obvious one

The paper optimizes per frame, then **averages the optima across all ports and
wavelengths** and re-decomposes with those shared values — except the quadratic
phase, which gets a linear fit in λ because defocus genuinely tracks wavelength.

This is not a tidiness preference. A transfer matrix is assembled *across*
frames, so coefficients measured against per-frame bases are not mutually
comparable and the TM does not describe one physical lantern. Implemented in
`MultiPortReconstructor.consolidate_parameters` / `reconstruct_all`
(`consistent_basis=True`, the default). Expect per-frame fidelity to dip
slightly — that is correct; the TM is what becomes trustworthy.

## Known physics discrepancy — read before quoting a fidelity

The two engines disagree about the lantern in front of them:

| | core radius | NA | LP modes |
|---|---|---|---|
| single-frame (`processing.*`) | 1.7e-5 | 0.11 | **15** |
| multiport (`processing.multiport.*`) | 1.2e-5 | 0.11 | **8** |

An N-port lantern supports ~N modes; a basis larger than that absorbs noise and
**inflates fidelity**. Measured on `tests/fixtures/sample_hologram.npy`:
15 modes → 0.9717, 8 modes → 0.9497. So ~2 points of the current number is
basis size, not optics.

The rig's lantern is 7-port (the archived datasets are 6- and 7-port), which
implies 8 modes and the multiport values. The single-frame config was left at
the paper's larger fiber. **Resolving this is a bench call, not a code call** —
it changes the pinned `GOLDEN_FIDELITY` in `tests/test_reconstruction.py`, so
change both together and say why in the commit.

### The missing 1.2 points — and the trap in closing them

Caleb's own analysis of this dataset is recoverable from the `002_Holography`
archive at `10-17-2023-Wavelengths/wavelengthDecompUpdatedLPModesForOne`
`PolarizationCleanupTimeAgain.py`. His parameters, now our defaults:

    cropSize 512 · modeSize 256 · Nfft 128 · sample_limit 32
    coreRadius 17.5e-6 · NA 0.13 · rIndex 1.453 · diameter 63-70
    makeButtersworth(Nfft, Nfft//2, Nfft//2, wc=15)

Run with exactly those, this code gets 96.76% ± 0.95%, not 98%. The fiber spec
is **not** the cause: his 17.5 µm/NA 0.13 and the 16.3 µm/NA 0.15 previously
hard-coded here both give the paper's 23-mode basis, and both land ~96.5–96.8%.

**The trap:** setting `butter_wc=4` yields 98.3% ± 0.5% and looks like a fix. It
is not what he did, and it pushes the consolidated mode-field diameter to index
0 — the edge of the search range — which is what a parameter absorbing someone
else's error looks like. Fidelity (Eq. 5) compares the recovered field to *its
own* LP reconstruction, so narrowing the passband can raise η by deleting
content the basis could never represent. Same failure mode as an oversized
basis, opposite direction. Don't do it; find the real cause.

Untested candidates: `sample_limit` (he passes 32 in the per-frame loop but
`Nfft` in one single-frame call), `filterDCComponents` `lineFilterWidth` (his
tutorial uses 3, we use 1), and his per-frame optimisation schedule.

## Layout

```
main.py                     launcher; imports gui.runtime first for its bootstrap
gui/                        PySide6 app; HolographyApp is composed from mixins
  runtime.py                frozen-build paths, Xeneth DLL path, sys.path, logfile
  experiment.py             acquisition loop (collect) + Process button
pipeline.py                 shared processing pipeline  <- change behavior HERE
process.py                  headless CLI over any folder of holograms
data_processing.py          single-frame engine (not a CLI)
multiport_reconstruction.py cross-port engine + transfer matrix
fringe_detection.py         fringe metrics + polarization coordinate-ascent
hardware/                   drivers: laser (GPIB), camera (GigE), switch, motors
lib/calebsUsefulFunctions.py  LP modes, FFT helpers, fidelity — the math library
lib/MMF.py                  multimode-fiber mode solver
lib/xenics/                 vendored Xeneth SDK Python wrapper — don't edit
```

## Conventions and traps

- **Threading:** worker threads never touch widgets. They call `self._post(msg)`,
  a Qt signal delivered on the GUI thread by `ShellMixin._dispatch_msg`.
- **Frames are 320×256**, but Caleb's FFT helpers assume square — the pipeline
  center-crops before using them.
- **`makeButterworth(N, centerX, centerY)` takes (col, row)**, not (row, col).
  Its own comment says the axes are flipped. Check the order at every call.
- **16-bit images:** load with `np.asarray(Image.open(p))`. Never
  `convert('L')` — it clips to 8-bit and saturates the frame.
- **Saturated frames are physically invalid**: clipping makes the recorded
  intensity nonlinear in the field, so the sideband and the recovered phase are
  both wrong. `check_saturation` flags them; they are saved but marked.
- **Camera "connects but no frames"** is the Windows Firewall blocking inbound
  GigE, or Xeneth holding the camera. Not a light or exposure problem.
- Config keys are all live. If you add one, wire it up — a knob that silently
  does nothing already cost this repo ten of them.

## Testing

`uv run pytest` — fast, no hardware. `tests/test_reconstruction.py` pins the
reconstruction against a real committed frame; if that fidelity moves, the
physics changed, so update the constant *and* explain it. The heavy multiport
test auto-skips without Caleb's archived dataset (gitignored, multi-GB).
