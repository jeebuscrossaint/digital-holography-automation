# -*- coding: utf-8 -*-
"""Single-frame hologram reconstruction — the engine, not a CLI.

Recovers the complex field from one off-axis hologram and decomposes it onto
the LP-mode basis, following Dobias et al., Opt. Express 34(9) 17217 (2026),
Sec. 2:

    FFT the intensity -> isolate the off-axis sideband -> demodulate to
    baseband -> Butterworth low-pass -> inverse FFT -> optimize (field
    position, mode-field diameter, quadratic phase) -> LP decomposition
    -> fidelity eta = |<E_rec, E_S>|^2  (Eq. 5)

This sees one frame at a time, which is what limits it: the carrier centroid
has to be estimated from that frame alone. ``multiport_reconstruction`` does
better by averaging the carrier across ports, and ``pipeline`` picks between
them. To process a folder, use ``process.py``.
"""

import sys
import numpy as np
import matplotlib.pyplot as plt
import yaml
from pathlib import Path
from scipy import ndimage, signal

_ROOT = Path(__file__).parent
_lib = str(_ROOT / 'lib')
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from calebsUsefulFunctions import (  # noqa: E402
    pltBoth, generateModes, filterDCComponents, generatePhaseMask, modeDecomp,
    combinedOutput, normalizeIntensity, overlap2FieldsV2, findBestOffset,
    generateMask, makeButterworth, getMaxIndex, getBlurredCentroid, rollMatrix,
)


class HolographyDataProcessor:
    """Automated processor for holography data"""
    
    def __init__(self, config_file='experiment_config.yaml'):
        """Initialize processor with configuration"""
        # Load configuration
        with open(config_file, 'r') as f:
            self.config = yaml.safe_load(f)
        
        self.data_dir = Path(self.config['data']['output_dir'])
        self.results_dir = self.data_dir / 'processed_results'
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
        # Processing parameters
        self.proc_config = self.config['processing']

        # --- reconstruction settings (Dobias et al., Opt. Express 2026) ---
        # float() guards YAML reading e-notation as a string.
        # crop_size = the window (px) kept around the beam. Too small and the
        # mode's outer structure is cropped off, which caps fidelity; 200 px
        # captures the full field on a 256-px frame. Clamped to the frame size
        # at process time.
        self._grid        = int(self.proc_config.get('crop_size', 200))
        self._core_radius = float(self.proc_config.get('core_radius', 1.7e-5))
        self._NA          = float(self.proc_config.get('numerical_aperture', 0.11))
        self._n_eff       = float(self.proc_config.get('effective_index', 1.453))
        # Cap on basis size. The basis should match the mode count the lantern
        # physically supports (core_radius/NA set that) — a larger basis just
        # overfits noise and inflates fidelity. See CLAUDE.md.
        self._num_modes   = int(self.proc_config.get('num_modes', 18))
        # Parameters optimized per-hologram to maximize fidelity (the paper
        # optimizes field position, mode-field diameter, and quadratic phase):
        self._lp_cuts = [22, 30, 40]                              # Butterworth cutoff (px)
        # FOV scan; sets the mode-field diameter on the grid (pixel size = fov/grid).
        self._fovs    = [round(v, 9) for v in np.arange(20e-6, 130e-6, 10e-6)]
        # Quadratic-phase factor k (defocus). Scanned over the configured range.
        lo, hi = self.proc_config.get('phase_factor_range', [-3.0, 3.0])
        step = float(self.proc_config.get('phase_factor_step', 0.5)) or 0.5
        self._phases = np.arange(float(lo), float(hi) + step / 2, step)
        self._mode_cache = {}
        self._opt_modes = None
        # self.modes generated lazily per-FOV during optimization (_modes_at).
        
    def _modes_at(self, fov, wavelength=1.55e-6):
        """LP-mode basis at a given field-of-view (sets mode-field diameter on
        the grid). Cached, since the optimizer reuses the same FOV set."""
        key = (round(fov, 9), round(wavelength, 12))
        if key not in self._mode_cache:
            self._mode_cache[key] = generateModes(
                N=self._grid, pxz=fov / self._grid, coreRadius=self._core_radius,
                NA=self._NA, wavelength=wavelength, rIndex=self._n_eff)
        return self._mode_cache[key]

    def _recover_field(self, hologram, lp_cut, lp_order=4, dc_diameter=40):
        """Off-axis recovery (Dobias et al., Opt. Express 2026, Sec. 2): FFT the
        raw intensity, locate the twin sideband sub-pixel, demodulate it to DC,
        Butterworth low-pass to isolate it, IFFT to the complex field. Returns
        (ES, centroid, selection).

        FFT the intensity directly — do NOT sqrt it.

        The carrier must be found by zeroing the DC cross and centre disk, then
        disk-blurring, then taking a Butterworth-weighted sub-pixel centroid.
        A raw argmax outside a small disk is not good enough: on a low-contrast
        frame the residual DC skirt outshines the true sideband, so it locks
        onto DC and demodulates around it, producing ~1% fidelity."""
        H = hologram.astype(float)
        N = H.shape[0]
        F = np.fft.fftshift(np.fft.fft2(H))
        cy, cx = N // 2, N // 2
        # Kill the DC cross + center disk, blur, then pick the brightest lobe
        # (the off-axis sideband). getMaxIndex returns (row, col).
        Pdc = filterDCComponents(np.abs(F).astype(float), 1, dc_diameter)
        blur = signal.convolve2d(Pdc, generateMask(15, 15), mode='same')
        pky, pkx = getMaxIndex(blur)
        # Butterworth-weight around that lobe and take the sub-pixel centroid
        # (makeButterworth's center is (X=col, Y=row) -> pass (pkx, pky)).
        bw = makeButterworth(N, pkx, pky, wc=15)
        cyy, cxx = ndimage.center_of_mass(blur * bw)
        u0, v0 = (cxx - cx) / N, (cyy - cy) / N               # carrier freq (cyc/px)
        Y, X = np.mgrid[0:N, 0:N]
        demod = H * np.exp(-2j * np.pi * (u0 * X + v0 * Y))    # shift twin -> DC
        Sd = np.fft.fftshift(np.fft.fft2(demod)) * makeButterworth(
            N, cx, cy, wc=lp_cut, n=lp_order)                 # verified Butterworth
        # Sd = the isolated sideband (the "FFT selection"); ES = its inverse FFT.
        return np.fft.ifft2(np.fft.ifftshift(Sd)), (cyy, cxx), Sd

    def _center_on_beam(self, ES, size):
        """Crop a size×size window centered on the beam, via getBlurredCentroid
        (disk-blur then sub-pixel center_of_mass). The blur matters: a lantern
        output is often fragmented into lobes, and a raw intensity centroid
        lands in the dark gap between them."""
        _, _, (cy, cx) = getBlurredCentroid(np.abs(ES), size)
        cy, cx = int(round(cy)), int(round(cx))
        N = ES.shape[0]
        y0 = min(max(cy - size // 2, 0), N - size)
        x0 = min(max(cx - size // 2, 0), N - size)
        return ES[y0:y0 + size, x0:x0 + size]


    def load_hologram(self, filepath):
        """Load hologram image from file
        
        Args:
            filepath: Path to .npy file
            
        Returns:
            2D numpy array
        """
        data = np.load(filepath)
        return data
    
    def process_single_hologram(self, hologram, wavelength_nm=1550,
                                show_plots=False, save_plots=False,
                                plot_prefix='', background=None, bg_modifier=1.0):
        """Process a single hologram image

        Args:
            hologram: 2D array of hologram intensity
            wavelength_nm: Wavelength in nanometers
            show_plots: Whether to display plots
            save_plots: Whether to save plot images
            plot_prefix: Prefix for saved plot filenames
            background: optional reference/background frame (same shape) to
                subtract before reconstruction — removes the low-frequency
                beam envelope/oscillations. Capture it as the reference beam
                alone, ideally one per wavelength.
            bg_modifier: scale on the background subtraction (nominally 1).

        Returns:
            Dictionary with processing results
        """
        results = {}

        hologram = np.asarray(hologram).astype(float)

        # Optional background subtraction: field = frame - background*modifier.
        # Kills the low-freq envelope that drags fidelity down. Background is
        # wavelength-dependent, so pass the reference taken at THIS wavelength.
        if background is not None:
            bg = np.asarray(background, dtype=float)
            if bg.shape == hologram.shape:
                hologram = hologram - bg * float(bg_modifier)
            else:
                print(f"  [bg] skipped — background shape {bg.shape} != frame {hologram.shape}")

        # Center-crop to a square — the FFT helpers (filterDCComponents,
        # findCentroid, generateMask) assume a square frame, but the Bobcat
        # 320 is 320x256. Without this the DC mask can't broadcast.
        h, w = hologram.shape[:2]
        if h != w:
            s = min(h, w)
            y0, x0 = (h - s) // 2, (w - s) // 2
            hologram = hologram[y0:y0 + s, x0:x0 + s]

        # Clamp the crop window to the frame — the window can't be bigger than
        # the (square) frame, or _center_on_beam's slice goes out of bounds.
        if self._grid > hologram.shape[0]:
            self._grid = hologram.shape[0]
            self._mode_cache.clear()

        wl_m = float(wavelength_nm) * 1e-9
        results['fft_field'] = np.fft.fftshift(np.fft.fft2(hologram.astype(float)))

        # Off-axis recovery + parameter optimization (the paper iterates over
        # Butterworth cutoff, mode-field diameter/FOV, and the quadratic-phase
        # factor, keeping the combination with the highest fidelity).
        print("  Recovering field + optimizing (Butterworth cutoff, mode "
              "diameter, quadratic phase)...")
        grid = self._grid
        # Quadratic-phase masks depend only on (grid, phase) — precompute the
        # 13 unique masks once instead of regenerating one per (lp, fov, phase).
        phase_masks = {float(pf): generatePhaseMask(grid, pf)
                       for pf in self._phases}
        best = None
        for lp in self._lp_cuts:
            ES_full, centroid, sel = self._recover_field(hologram, lp)
            base = normalizeIntensity(self._center_on_beam(ES_full, grid))
            for fov in self._fovs:
                modes = self._modes_at(fov, wl_m)
                nm = min(self._num_modes, modes.shape[0])
                for pf in self._phases:
                    fld = normalizeIntensity(base * phase_masks[float(pf)])
                    dec = modeDecomp(fld, modes, nm)
                    rec = combinedOutput(modes[:nm], dec)
                    fid = abs(overlap2FieldsV2(fld, rec)) ** 2     # paper's eta (Eq 5)
                    if best is None or fid > best['fidelity']:
                        best = dict(fidelity=fid, lp=lp, fov=fov, phase=float(pf),
                                    nm=nm, field=fld, recomp=normalizeIntensity(rec),
                                    decomp=dec, recovered_full=ES_full,
                                    recovered_centered=base, selection=sel,
                                    centroid=centroid, modes=modes)

        # Field-position refinement (paper Sec. 2): roll the winning field to
        # best-fit the mode basis.
        b_modes, b_nm = best['modes'], best['nm']
        xo, yo = findBestOffset(best['field'], b_modes[:b_nm],
                                -6, 6, -6, 6, 1)
        if xo or yo:
            fld_ro = normalizeIntensity(rollMatrix(best['field'], xo, yo))
            dec_ro = modeDecomp(fld_ro, b_modes, b_nm)
            rec_ro = combinedOutput(b_modes[:b_nm], dec_ro)
            fid_ro = abs(overlap2FieldsV2(fld_ro, rec_ro)) ** 2
            if fid_ro > best['fidelity']:
                best.update(fidelity=fid_ro, field=fld_ro, decomp=dec_ro,
                            recomp=normalizeIntensity(rec_ro),
                            offset=(int(xo), int(yo)))

        self._opt_modes = best['modes']
        decomp = best['decomp']
        results['recovered_field'] = best['recovered_full']
        results['recovered_centered'] = best['recovered_centered']  # for the key figure
        results['fft_selection'] = best['selection']                # isolated sideband
        results['recovered_field_corrected'] = best['field']
        results['reconstructed_field'] = best['recomp']
        results['mode_decomposition'] = decomp
        results['fidelity'] = best['fidelity']
        results['twin_centroid'] = best['centroid']
        results['best_params'] = {k: best[k] for k in ('lp', 'fov', 'phase', 'nm')}

        mode_powers = np.abs(decomp) ** 2
        results['mode_powers'] = (mode_powers / np.sum(mode_powers)
                                  if mode_powers.sum() > 0 else mode_powers)

        print(f"    Fidelity {best['fidelity']:.3f}  "
              f"(cutoff={best['lp']}, fov={best['fov']:.1e} m, "
              f"phase={best['phase']:+.2f}, {best['nm']} modes)")
        
        # Generate plots
        if show_plots or save_plots:
            self.generate_plots(hologram, results, 
                               show=show_plots, 
                               save=save_plots,
                               prefix=plot_prefix)
        
        return results
    
    def generate_plots(self, hologram, results, show=True, save=False, prefix=''):
        """Generate visualization plots
        
        Args:
            hologram: Original hologram image
            results: Processing results dictionary
            show: Display plots
            save: Save plots to file
            prefix: Filename prefix for saved plots
        """
        # The full reconstruction breakdown in one image (2x4):
        #   1 original   2 FFT+carrier   3 FFT selection   4 recovered field
        #   5 recovered + corrections (phase + bg)   6 recomposition + fidelity
        #   7 LP01 reference   8 mode-power distribution
        modes = self._opt_modes if self._opt_modes is not None else []
        recov = results.get('recovered_centered', results['recovered_field_corrected'])
        plt.figure(figsize=(16, 8))

        ax = plt.subplot(2, 4, 1)
        ax.imshow(hologram, cmap='gray'); ax.set_title('1. Original hologram')
        ax.set_xticks([]); ax.set_yticks([])

        ax = plt.subplot(2, 4, 2)
        ax.imshow(np.log10(np.abs(results['fft_field']) + 1), cmap='magma')
        c = results.get('twin_centroid')
        if c is not None:
            ax.plot(c[1], c[0], 'cx', markersize=12, markeredgewidth=2)
        ax.set_title('2. FFT (log) + carrier'); ax.set_xticks([]); ax.set_yticks([])

        ax = plt.subplot(2, 4, 3)
        sel = results.get('fft_selection')
        if sel is not None:
            ax.imshow(np.log10(np.abs(sel) + 1), cmap='magma')
        ax.set_title('3. FFT selection (demod + Butterworth)')
        ax.set_xticks([]); ax.set_yticks([])

        plt.subplot(2, 4, 4)
        pltBoth(recov); plt.title('4. iFFT recovered field (amp+phase)')

        plt.subplot(2, 4, 5)
        pltBoth(results['recovered_field_corrected'])
        plt.title('5. iFFT + corrections (phase + bg)')

        plt.subplot(2, 4, 6)
        pltBoth(results['reconstructed_field'])
        plt.title(f"6. Recomposition  (η = {results['fidelity']*100:.1f}%)")

        plt.subplot(2, 4, 7)
        if len(modes):
            pltBoth(modes[0])
        plt.title('7. LP01 mode (reference)')

        ax = plt.subplot(2, 4, 8)
        mp = results['mode_powers']
        ax.bar(range(len(mp)), np.asarray(mp) * 100)
        ax.set_xlabel('LP mode'); ax.set_ylabel('Power (%)')
        ax.set_title('8. Mode power distribution'); ax.grid(True, alpha=0.3)

        plt.tight_layout()
        
        if save and prefix:
            plot_path = self.results_dir / f'{prefix}_analysis.png'
            plt.savefig(plot_path, dpi=150, bbox_inches='tight')
            print(f"  [saved] Plot: {plot_path}")
        
        if show:
            plt.show()
        else:
            plt.close()
    

if __name__ == '__main__':
    raise SystemExit(
        "data_processing is the single-frame reconstruction engine, not a CLI.\n"
        "To process a folder of holograms:  python process.py <folder>")
