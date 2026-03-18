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


class HolographyDataProcessor:
    """Automated processor for holography data"""
    
    def __init__(self, config_file='experiment_config.yaml'):
        """Initialize processor with configuration"""
        # Load configuration
        with open(config_file, 'r') as f:
            self.config = yaml.safe_load(f)
        
        self.data_dir = Path(self.config['data']['output_dir'])
        self.results_dir = self.data_dir / 'processed_results'
        self.results_dir.mkdir(exist_ok=True)
        
        # Processing parameters
        self.proc_config = self.config['processing']
        
        # Generate LP modes for decomposition
        print("Generating LP mode basis...")
        self.generate_lp_modes()
        
    def generate_lp_modes(self):
        """Generate LP mode basis for decomposition"""
        N = 100  # Matrix size
        core_radius = self.proc_config['core_radius']
        NA = self.proc_config['numerical_aperture']
        wavelength = 1550e-9  # Will adjust per image if needed
        n_eff = self.proc_config['effective_index']
        pxz = self.proc_config['pixel_size'] / N
        
        self.modes = generateModes(
            N=N,
            pxz=pxz,
            coreRadius=core_radius,
            NA=NA,
            wavelength=wavelength,
            rIndex=n_eff
        )
        
        print(f"  Generated {self.modes.shape[0]} LP modes")
    
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
                                plot_prefix=''):
        """Process a single hologram image
        
        Args:
            hologram: 2D array of hologram intensity
            wavelength_nm: Wavelength in nanometers
            show_plots: Whether to display plots
            save_plots: Whether to save plot images
            plot_prefix: Prefix for saved plot filenames
            
        Returns:
            Dictionary with processing results
        """
        results = {}
        
        # Convert to complex field (hologram is intensity only)
        field = np.sqrt(hologram.astype(float))
        
        # Step 1: Compute FFT
        print("  [1/6] Computing FFT...")
        fft_field = fft(field)
        fft_abs = np.abs(fft_field)
        
        results['fft_field'] = fft_field
        
        # Step 2: Find center and twin image centroids
        print("  [2/6] Finding twin image centroids...")
        
        # Find DC center (should be at image center)
        dc_center = np.array(fft_abs.shape) // 2
        
        # Find twin images in quadrants 2 and 4 (or 1 and 3)
        # Filter out DC components first
        fft_filtered = filterDCComponents(fft_abs.copy(), 
                                         lineFilterWidth=5, 
                                         centerFilterDiameter=40)
        
        # Find first twin image (quadrant 2 - upper right)
        _, _, _, centroid1 = findCentroid(fft_field, quadrant=2, maskSize=64)
        
        # Find second twin image (quadrant 4 - lower left)  
        _, _, _, centroid2 = findCentroid(fft_field, quadrant=4, maskSize=64)
        
        results['dc_center'] = dc_center
        results['twin1_centroid'] = centroid1
        results['twin2_centroid'] = centroid2
        
        print(f"    DC center: {dc_center}")
        print(f"    Twin 1: {centroid1}")
        print(f"    Twin 2: {centroid2}")
        
        # Step 3: Extract twin images
        print("  [3/6] Extracting twin images...")
        
        crop_size = self.proc_config['crop_size']
        
        twin1_cropped = cropArray(fft_field, centroid1, crop_size)
        twin2_cropped = cropArray(fft_field, centroid2, crop_size)
        
        # Step 4: Inverse FFT to get recovered field
        print("  [4/6] Recovering field from twin image...")
        
        # Use twin 1 (you could also use twin 2 or combine them)
        # Pad twin image back to full size centered at DC
        twin_padded = np.zeros_like(fft_field)
        center = np.array(twin_padded.shape) // 2
        start_x = center[0] - crop_size // 2
        start_y = center[1] - crop_size // 2
        twin_padded[start_x:start_x+crop_size, start_y:start_y+crop_size] = twin1_cropped
        
        # Recover field
        recovered_field = ifft(twin_padded)
        recovered_field = normalizeIntensity(recovered_field)
        
        results['recovered_field'] = recovered_field
        
        # Step 5: Phase correction (optional)
        print("  [5/6] Applying phase corrections...")
        
        if self.proc_config.get('quadratic_phase_correction'):
            # Try different phase factors to find best match
            # This would ideally be optimized, but we'll use a default
            phase_factor = 0.5  # Adjust as needed
            recovered_field_corrected = applyQuadraticPhase(recovered_field, phase_factor)
        else:
            recovered_field_corrected = recovered_field
        
        results['recovered_field_corrected'] = recovered_field_corrected
        
        # Step 6: Mode decomposition
        print("  [6/6] Mode decomposition...")
        
        # Resize recovered field to match mode size if needed
        if recovered_field_corrected.shape != self.modes[0].shape:
            # Simple crop/pad to match
            field_size = recovered_field_corrected.shape[0]
            mode_size = self.modes[0].shape[0]
            
            if field_size > mode_size:
                # Crop
                start = (field_size - mode_size) // 2
                field_for_decomp = recovered_field_corrected[start:start+mode_size, 
                                                             start:start+mode_size]
            else:
                # Pad
                field_for_decomp = np.zeros((mode_size, mode_size), dtype=complex)
                start = (mode_size - field_size) // 2
                field_for_decomp[start:start+field_size, start:start+field_size] = recovered_field_corrected
        else:
            field_for_decomp = recovered_field_corrected
        
        # Normalize
        field_for_decomp = normalizeIntensity(field_for_decomp)
        
        # Decompose
        num_modes = self.proc_config['num_modes']
        decomp = modeDecomp(field_for_decomp, self.modes, num_modes)
        
        # Reconstruct from modes
        recomp = combinedOutput(self.modes[:num_modes], decomp)
        recomp = normalizeIntensity(recomp)
        
        # Calculate fidelity
        fidelity = abs(overlap2FieldsV2(field_for_decomp, recomp))
        
        results['mode_decomposition'] = decomp
        results['reconstructed_field'] = recomp
        results['fidelity'] = fidelity
        
        print(f"    Decomposed into {num_modes} modes")
        print(f"    Reconstruction fidelity: {fidelity:.4f}")
        
        # Calculate mode powers
        mode_powers = np.abs(decomp) ** 2
        mode_powers_norm = mode_powers / np.sum(mode_powers)
        results['mode_powers'] = mode_powers_norm
        
        print(f"    Mode powers: {mode_powers_norm}")
        
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
        fig = plt.figure(figsize=(16, 12))
        
        # Original hologram
        plt.subplot(3, 4, 1)
        plt.imshow(hologram, cmap='gray')
        plt.title('Original Hologram')
        plt.colorbar()
        
        # FFT (log scale)
        plt.subplot(3, 4, 2)
        pltLogAbs(results['fft_field'])
        plt.title('FFT (log scale)')
        
        # Mark twin images on FFT
        plt.subplot(3, 4, 3)
        fft_abs = np.abs(results['fft_field'])
        plt.imshow(np.log10(fft_abs), cmap='viridis')
        plt.plot(results['twin1_centroid'][1], results['twin1_centroid'][0], 'rx', markersize=15)
        plt.plot(results['twin2_centroid'][1], results['twin2_centroid'][0], 'rx', markersize=15)
        plt.title('Twin Image Locations')
        
        # Recovered field (amplitude)
        plt.subplot(3, 4, 5)
        pltAbs(results['recovered_field'])
        plt.title('Recovered Field (Amplitude)')
        
        # Recovered field (phase)
        plt.subplot(3, 4, 6)
        pltAngle(results['recovered_field'])
        plt.title('Recovered Field (Phase)')
        
        # Recovered field (both)
        plt.subplot(3, 4, 7)
        pltBoth(results['recovered_field'])
        plt.title('Recovered Field (Amp+Phase)')
        
        # Corrected field
        plt.subplot(3, 4, 8)
        pltBoth(results['recovered_field_corrected'])
        plt.title('Phase-Corrected Field')
        
        # Reconstructed field from modes
        plt.subplot(3, 4, 9)
        pltBoth(results['reconstructed_field'])
        plt.title(f"Reconstructed (Fidelity={results['fidelity']:.3f})")
        
        # Mode powers bar chart
        plt.subplot(3, 4, 10)
        mode_powers = results['mode_powers']
        plt.bar(range(len(mode_powers)), mode_powers * 100)
        plt.xlabel('Mode Number')
        plt.ylabel('Power (%)')
        plt.title('Mode Power Distribution')
        plt.grid(True, alpha=0.3)
        
        # Show first few LP modes for reference
        num_modes_show = min(6, self.modes.shape[0])
        for i in range(num_modes_show):
            plt.subplot(3, 6, 13 + i)
            pltBoth(self.modes[i])
            plt.title(f'LP Mode {i}', fontsize=8)
        
        plt.tight_layout()
        
        if save and prefix:
            plot_path = self.results_dir / f'{prefix}_analysis.png'
            plt.savefig(plot_path, dpi=150, bbox_inches='tight')
            print(f"  💾 Plot saved: {plot_path}")
        
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
                
                print(f"  ✓ Completed")
                
            except Exception as e:
                print(f"  ✗ Error processing {filepath.name}: {e}")
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
    
    print("\n✓ Processing finished.\n")


if __name__ == '__main__':
    main()
