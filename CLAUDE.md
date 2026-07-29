# CLAUDE.md

Measuring the wavelength-dependent transfer matrix of a photonic lantern by
off-axis digital holography, at UCF CREOL. Reproduces Dobias et al.,
*Opt. Express* **34**(9) 17217 (2026) — arXiv:2604.22091. Read it before
touching reconstruction code.

Answer short. Lead with the answer, skip status reports, commit to `main`
without asking — it's a solo repo and everything is in git. Do ask about bench
facts you can't check (lantern port count, fiber spec).

## Where things are

```
main.py        launcher            pipeline.py    <- change processing HERE
gui/           PySide6 app         process.py     headless CLI over a folder
hardware/      instrument drivers  data_processing.py        single-frame engine
lib/           LP modes, FFT math  multiport_reconstruction.py  cross-port + TM
```

Two reconstruction engines. Single-frame sees one hologram, so it estimates the
carrier from that frame alone. Multiport needs >=2 legs and is far better: the
carrier is common to every port, so averaging the sideband across ports per
wavelength and line-fitting vs lambda pins it, then Fourier fine-binning
resamples sub-pixel. `pipeline.py` runs both and keeps the better per frame —
change behaviour there, not in a front end.

`uv run pytest` — fast, no hardware.

**Exploring: use `git ls-files`, never `find` or `ls -R`.** 93 files are tracked;
the working tree holds ~17,500, because `002_Holography_full/` (16k files, 37 GB)
and `_caleb_ref/` are gitignored reference data that `tests/test_multiport.py`
reads. `find . -type f` emits 2.3 MB and will eat your context; `git ls-files` is
2.4 KB. Grep/ripgrep already honour `.gitignore` and are safe. Those trees also
contain multi-GB `.spydata`/`.pkl` binaries and filenames with spaces — never
`cat`/`head` into them, and quote any path you pass to a shell.

## Traps

- **Don't sqrt the intensity** before the FFT. FFT the raw frame.
- **`makeButterworth(N, centerX, centerY)` is (col, row)**, not (row, col).
- **16-bit images:** `np.asarray(Image.open(p))`. Never `convert('L')` — clips to
  8-bit and saturates the frame.
- **Saturated frames are invalid physics** — clipping makes intensity nonlinear
  in the field, so amplitude and phase are both wrong.
- **Camera connects but no frames** = Windows Firewall blocking inbound GigE, or
  Xeneth holding the camera. Not a light problem.
- Worker threads never touch widgets — they call `self._post(msg)`.
- Frames are 320x256; the FFT helpers assume square, so the pipeline crops.

## Two open physics questions

**1. Mode count is probably wrong.** Single-frame uses core 1.7e-5 / NA 0.11 =
**15 modes** at 1550 nm (17 below 1550 — V goes as 1/lambda, so the basis size
changes across the sweep); multiport uses 1.2e-5 / 0.11 = **8**. Same lantern.
An N-port
lantern has ~N modes, so a 7-port rig means 8 and the extra 7 just absorb noise
and inflate fidelity (measured: 15 modes 0.9717, 8 modes 0.9497 on the same
frame). Needs the bench answer, then update `GOLDEN_FIDELITY` in the same commit.

A third parameter set exists and is *not* a fourth opinion: the
`MultiPortReconstructor` signature defaults to 17.5e-6 / 0.13 → **23 modes**,
which is the *paper's* 19-port lantern, used only by `tests/test_multiport.py`
against Caleb's archive. `pipeline.run_multiport` overrides it to this rig's
1.2e-5 / 0.11. Don't "reconcile" those two — they describe different lanterns.

**2. Don't chase the paper's 98%.** Multiport gets 96.76% on Caleb's archive;
his own saved run gets 96.89%. We match him — carrier centroids identical to
0.000 px, twin image |overlap| 1.000000, decomposition cosine sim 0.997-0.9998
(`tests/test_multiport.py`). The gap to the printed 98% is between his 2023
analysis and the paper, not a bug here. Setting `butter_wc=4` "fixes" it to
98.3% by deleting field content the basis can't represent — same overfitting as
too many modes. Defaults are his published values; leave them.
