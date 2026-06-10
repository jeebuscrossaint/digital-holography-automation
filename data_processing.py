# -*- coding: utf-8 -*-
"""
Automated Data Processing Pipeline for Digital Holography
Processes hologram images to extract mode decomposition

Workflow:
1. Load hologram images
2. Compute FFT
3. Find twin image centroids
4. Extract and interpolate twin images
5. Apply phase corrections
6. Mode decomposition with LP modes
7. Save results and generate plots

Author: Amarnath & GitHub Copilot
Date: March 2026
"""

import sys
import os
import numpy as np
import matplotlib.pyplot as plt
import yaml
from pathlib import Path
from scipy import ndimage, signal
from datetime import datetime

from pathlib import Path as _Path
_ROOT = _Path(__file__).parent
_lib = str(_ROOT / 'lib')
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from MMF import MMF
from calebsUsefulFunctions import (
    fft, ifft, pltAbs, pltAngle, pltBoth, pltLogAbs,
    generateModes, findCentroid, cropArray, filterDCComponents,
    generatePhaseMask, applyQuadraticPhase, modeDecomp,
    combinedOutput, normalizeIntensity, overlap2FieldsV2,
    decompAndRecomp, findBestOffset
)


def _butter_lp(N, D0, order=4):
    """Butterworth low-pass mask (centered), used to isolate the demodulated
    twin from DC and noise (Opt. Express 2026 uses a Butterworth filter)."""
    y, x = np.ogrid[:N, :N]
    r = np.hypot(y - N // 2, x - N // 2)
    return 1.0 / (1.0 + (r / D0) ** (2 * order))


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
        # crop_size = the window (px) kept around the beam. This is the "zoom":
        # too small and you crop the mode's outer structure off and cap fidelity
        # (Caleb: "your image is still very zoomed in ... cropping something
        # twice"). 200 px captures the full field on a 256-px frame and lifts
        # fidelity ~92% -> ~96%. Clamped to the frame size at process time.
        self._grid        = int(self.proc_config.get('crop_size', 200))
        self._core_radius = float(self.proc_config.get('core_radius', 1.7e-5))
        self._NA          = float(self.proc_config.get('numerical_aperture', 0.11))
        self._n_eff       = float(self.proc_config.get('effective_index', 1.453))
        self._num_modes   = int(self.proc_config.get('num_modes', 18))
        # Parameters optimized per-hologram to maximize fidelity (the paper
        # optimizes field position, mode-field diameter, and quadratic phase):
        self._lp_cuts = [22, 30, 40]                              # Butterworth cutoff (px)
        # FOV scan widened to match the bigger window so the mode can fill it.
        self._fovs    = [round(v, 9) for v in np.arange(20e-6, 130e-6, 10e-6)]
        self._phases  = np.arange(-3.0, 3.01, 0.5)               # quadratic-phase factor k
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

    def _recover_field(self, hologram, lp_cut, lp_order=4, dc_radius=18):
        """Off-axis recovery (Opt. Express 2026, Sec. 2): FFT the raw intensity,
        locate the twin sideband sub-pixel, demodulate it to DC, Butterworth
        low-pass to isolate it, IFFT to the complex field. Returns (ES, centroid).
        NOTE: FFT the intensity directly — do NOT sqrt it (that was the old bug)."""
        H = hologram.astype(float)
        N = H.shape[0]
        P = np.abs(np.fft.fftshift(np.fft.fft2(H)))
        cy, cx = N // 2, N // 2
        yy, xx = np.ogrid[:N, :N]
        Pm = P.copy()
        Pm[np.hypot(yy - cy, xx - cx) <= dc_radius] = 0       # mask DC to find carrier
        py, px = np.unravel_index(int(Pm.argmax()), Pm.shape)
        w = 6                                                  # sub-pixel refine
        # Clamp the window to the array — if the carrier is within w px of an
        # edge, negative slice indices would wrap to the far edge and give a
        # bogus centroid (wrong carrier freq -> wrong reconstruction).
        y0, y1 = max(py - w, 0), min(py + w + 1, N)
        x0, x1 = max(px - w, 0), min(px + w + 1, N)
        sub = Pm[y0:y1, x0:x1]
        dy, dx = ndimage.center_of_mass(sub)
        cyy, cxx = y0 + dy, x0 + dx
        u0, v0 = (cxx - cx) / N, (cyy - cy) / N               # carrier freq (cyc/px)
        Y, X = np.mgrid[0:N, 0:N]
        demod = H * np.exp(-2j * np.pi * (u0 * X + v0 * Y))    # shift twin -> DC
        Sd = np.fft.fftshift(np.fft.fft2(demod)) * _butter_lp(N, lp_cut, lp_order)
        # Sd = the isolated sideband (the "FFT selection"); ES = its inverse FFT.
        return np.fft.ifft2(np.fft.ifftshift(Sd)), (cyy, cxx), Sd

    def _center_on_beam(self, ES, size):
        """Crop a size×size window centered on the field's intensity centroid."""
        cy, cx = ndimage.center_of_mass(np.abs(ES) ** 2)
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
                beam envelope/oscillations (Caleb's tip). Capture it as the
                reference beam alone, ideally one per wavelength.
            bg_modifier: scale on the background subtraction (Caleb: "hopefully
                it's 1").

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

        # Center-crop to a square — Caleb's FFT helpers (filterDCComponents,
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
        # The reconstruction breakdown Caleb asked for, in one image (2x4):
        #   1 original   2 FFT+carrier   3 FFT selection   4 recovered field
        #   5 recovered + corrections (phase + bg)   6 recomposition + fidelity
        #   7 LP01 reference   8 mode-power distribution
        modes = self._opt_modes if self._opt_modes is not None else []
        recov = results.get('recovered_centered', results['recovered_field_corrected'])
        fig = plt.figure(figsize=(16, 8))

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
    
    def process_dataset(self, show_plots=False, save_plots=True):
        """Process all holograms in dataset
        
        Args:
            show_plots: Display plots interactively
            save_plots: Save plots to files
        """
        # Find all .npy files in data directory
        hologram_files = sorted(self.data_dir.glob('leg*.npy'))
        
        if len(hologram_files) == 0:
            print(f"No hologram files found in {self.data_dir}")
            return
        
        print("=" * 60)
        print(f"PROCESSING {len(hologram_files)} HOLOGRAMS")
        print("=" * 60 + "\n")
        
        all_results = []
        
        for i, filepath in enumerate(hologram_files):
            print(f"\n[{i+1}/{len(hologram_files)}] Processing: {filepath.name}")
            
            # Load metadata if available
            metadata_file = filepath.with_suffix('.yaml')
            wavelength_nm = 1550  # default
            
            if metadata_file.exists():
                with open(metadata_file, 'r') as f:
                    metadata = yaml.safe_load(f)
                    wavelength_nm = metadata.get('wavelength_nm', 1550)
            
            # Load hologram
            hologram = self.load_hologram(filepath)
            
            # Process
            try:
                results = self.process_single_hologram(
                    hologram,
                    wavelength_nm=wavelength_nm,
                    show_plots=show_plots,
                    save_plots=save_plots,
                    plot_prefix=filepath.stem
                )
                
                results['filename'] = filepath.name
                results['filepath'] = str(filepath)
                
                # Save results
                results_file = self.results_dir / f'{filepath.stem}_results.npz'
                np.savez(results_file,
                        mode_decomposition=results['mode_decomposition'],
                        mode_powers=results['mode_powers'],
                        fidelity=results['fidelity'],
                        recovered_field=results['recovered_field_corrected'])
                
                all_results.append(results)
                
                print(f"  [ok] Completed")
                
            except Exception as e:
                print(f"  [error] processing {filepath.name}: {e}")
                import traceback
                traceback.print_exc()
        
        # Save summary
        print("\n" + "=" * 60)
        print("PROCESSING COMPLETE")
        print("=" * 60)
        
        summary = {
            'processing_date': datetime.now().isoformat(),
            'total_processed': len(all_results),
            'results': []
        }
        
        for res in all_results:
            summary['results'].append({
                'filename': res['filename'],
                'fidelity': float(res['fidelity']),
                'mode_powers': res['mode_powers'].tolist()
            })
        
        summary_file = self.results_dir / 'processing_summary.yaml'
        with open(summary_file, 'w') as f:
            yaml.dump(summary, f)
        
        print(f"\nSummary saved: {summary_file}")
        print(f"Results directory: {self.results_dir}")
        
        return all_results


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Automated Data Processing for Digital Holography'
    )
    parser.add_argument(
        '--config',
        default='experiment_config.yaml',
        help='Path to configuration file'
    )
    parser.add_argument(
        '--show-plots',
        action='store_true',
        help='Display plots interactively'
    )
    parser.add_argument(
        '--no-save-plots',
        action='store_true',
        help='Do not save plots to files'
    )
    
    args = parser.parse_args()
    
    print("\n" + "=" * 60)
    print("DIGITAL HOLOGRAPHY DATA PROCESSOR")
    print("Photonic Lantern Mode Decomposition")
    print("=" * 60 + "\n")
    
    processor = HolographyDataProcessor(config_file=args.config)
    processor.process_dataset(
        show_plots=args.show_plots,
        save_plots=not args.no_save_plots
    )
    
    print("\n[done] Processing finished.\n")


if __name__ == '__main__':
    main()
