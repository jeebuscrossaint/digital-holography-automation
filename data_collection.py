# -*- coding: utf-8 -*-
"""
Automated Data Collection Pipeline for Digital Holography
Photonic Lantern Testbed

This script automates the data collection workflow:
1. Connect to all hardware (laser, camera, switch, motors)
2. Loop through each photonic lantern leg
3. For each leg, loop through wavelengths
4. For each wavelength, check fringes and adjust polarization if needed
5. Save images in standardized format

Author: Amarnath & GitHub Copilot
Date: March 2026
"""

import sys
import os
import time
import numpy as np
import yaml
from datetime import datetime
from pathlib import Path

from pathlib import Path as _Path
_ROOT = _Path(__file__).parent
for _p in (str(_ROOT / 'hardware'), str(_ROOT / 'lib')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from HPTunableLaserSource import HPTunableLaserSource
from XenicsCam import xCam, dev_discovery
from D700DiconSwitch import D700DiconSwitch
from polMotors import polMotors
from fringe_detection import check_fringes_visible, optimize_polarization_for_fringes


class HolographyDataCollector:
    """Main class for automated holography data collection"""
    
    def __init__(self, config_file='experiment_config.yaml'):
        """Initialize data collector with configuration
        
        Args:
            config_file: Path to YAML configuration file
        """
        # Load configuration
        with open(config_file, 'r') as f:
            self.config = yaml.safe_load(f)
        
        # Initialize hardware connections
        self.laser = None
        self.camera = None
        self.switch = None
        self.motors = None
        
        # Data storage
        self.output_dir = Path(self.config['data']['output_dir'])
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Metadata
        self.session_metadata = {
            'session_start': datetime.now().isoformat(),
            'config': self.config
        }
        
        self.collected_images = []
        
    def connect_hardware(self):
        """Initialize all hardware connections"""
        print("=" * 60)
        print("CONNECTING TO HARDWARE")
        print("=" * 60)
        
        # Laser
        print("\n[1/4] Connecting to HP Tunable Laser...")
        try:
            laser_addr = self.config['hardware']['laser']['gpib_address']
            self.laser = HPTunableLaserSource(laser_addr)
            
            # Set initial power
            power = self.config['hardware']['laser']['power_uw']
            unit = self.config['hardware']['laser']['power_unit']
            self.laser.changePowerUnit(unit)
            self.laser.powerAmplitude(power)
            
            print(f"  ✓ Laser connected: {laser_addr}")
            print(f"  Power: {power} {unit}")
        except Exception as e:
            print(f"  ✗ Laser connection failed: {e}")
            raise
        
        # Camera
        print("\n[2/4] Connecting to Xenics Camera...")
        try:
            cam_url = self.config['hardware']['camera'].get('url')
            if not cam_url or cam_url == "auto":
                cam_url = dev_discovery()
            
            self.camera = xCam(url=cam_url)
            print(f"  ✓ Camera connected")
            print(f"  PID: {self.camera.pid}, Serial: {self.camera.ser}")
        except Exception as e:
            print(f"  ✗ Camera connection failed: {e}")
            raise
        
        # Fiber Switch
        print("\n[3/4] Connecting to Dicon Fiber Switch...")
        try:
            port = self.config['hardware']['fiber_switch']['port']
            baudrate = self.config['hardware']['fiber_switch']['baudrate']
            self.switch = D700DiconSwitch(port=port, baudrate=baudrate)
            print(f"  ✓ Switch connected on {port}")
        except Exception as e:
            print(f"  ✗ Switch connection failed: {e}")
            raise
        
        # Polarization Motors
        print("\n[4/4] Connecting to Polarization Motors...")
        try:
            serial_num = self.config['hardware']['polarization_motors']['serial_number']
            self.motors = polMotors(serialNumber=serial_num.encode())
            
            # Home motors to initial positions
            initial_angles = self.config['hardware']['polarization_motors']['initial_angles']
            for i, angle in enumerate(initial_angles):
                self.motors.moveMotor(i+1, angle)
            
            while self.motors.isBusy():
                time.sleep(0.1)
            
            print(f"  ✓ Motors connected and homed")
        except Exception as e:
            print(f"  ✗ Motor connection failed: {e}")
            raise
        
        # Turn on laser output
        print("\n[*] Enabling laser output...")
        self.laser.outputState(True)
        print("  ✓ Laser output ON")
        
        print("\n" + "=" * 60)
        print("ALL HARDWARE CONNECTED SUCCESSFULLY")
        print("=" * 60 + "\n")
        
    def disconnect_hardware(self):
        """Safely disconnect all hardware"""
        print("\nDisconnecting hardware...")
        
        if self.laser:
            try:
                self.laser.outputState(False)
                print("  ✓ Laser output OFF")
            except:
                pass
        
        if self.camera:
            try:
                self.camera.stopCapture()
                self.camera.closeCamera()
                print("  ✓ Camera disconnected")
            except:
                pass
        
        if self.switch:
            try:
                self.switch.close()
                print("  ✓ Switch disconnected")
            except:
                pass
        
        print("Hardware disconnected.")
    
    def collect_data(self):
        """Main data collection loop
        
        Follows workflow:
        - For each leg in photonic lantern
          - For each wavelength
            - Check if fringes visible
            - If not, adjust polarization
            - Save image
        """
        legs = self.config['experiment']['legs']
        wavelengths = self.config['experiment']['wavelengths']
        wait_times = self.config['experiment']['wait_times']
        
        fringe_config = self.config['experiment']['fringe_detection']
        filename_format = self.config['data']['filename_format']
        
        total_acquisitions = len(legs) * len(wavelengths)
        current_acq = 0
        
        print("=" * 60)
        print(f"STARTING DATA COLLECTION")
        print(f"Legs: {len(legs)}, Wavelengths: {len(wavelengths)}")
        print(f"Total images: {total_acquisitions}")
        print("=" * 60 + "\n")
        
        module = self.config['hardware']['fiber_switch']['module']
        
        for leg in legs:
            print(f"\n{'='*60}")
            print(f"LEG {leg}")
            print(f"{'='*60}")
            
            # Switch to this leg
            self.switch.move_to_position(module, leg)
            time.sleep(wait_times['after_leg_switch'])
            
            for wavelength in wavelengths:
                current_acq += 1
                print(f"\n[{current_acq}/{total_acquisitions}] Leg {leg}, λ = {wavelength} nm")
                
                # Set wavelength
                self.laser.changeWavelength(wavelength)
                time.sleep(wait_times['after_wavelength_change'])
                
                # Check for fringes
                frame = self.camera.getFrame()
                if frame is None:
                    print("  ✗ Failed to capture frame, skipping...")
                    continue
                
                fringes_visible = False
                metric = 0
                
                if fringe_config['enabled']:
                    method = fringe_config['check_method']
                    threshold = fringe_config['min_visibility']
                    
                    fringes_visible, metric = check_fringes_visible(
                        frame, method=method, threshold=threshold
                    )
                    
                    print(f"  Fringe check: {method} = {metric:.3f} (threshold={threshold})")
                    
                    if not fringes_visible:
                        print(f"  ⚠ Fringes not visible, adjusting polarization...")
                        
                        success, best_metric, best_angles = optimize_polarization_for_fringes(
                            self.camera, 
                            self.motors,
                            max_attempts=fringe_config['max_attempts'],
                            method=method,
                            threshold=threshold
                        )
                        
                        if success:
                            print(f"  ✓ Polarization optimized: {best_angles}, metric={best_metric:.3f}")
                            # Capture new frame with optimized polarization
                            time.sleep(wait_times['after_polarization_adjust'])
                            frame = self.camera.getFrame()
                            fringes_visible = True
                            metric = best_metric
                        else:
                            print(f"  ⚠ Could not achieve good fringes (best: {best_metric:.3f})")
                    else:
                        print(f"  ✓ Fringes visible!")
                
                # Save image
                filename = filename_format.format(leg=leg, wavelength=wavelength)
                filepath = self.output_dir / filename
                
                np.save(filepath, frame)
                
                # Save metadata
                if self.config['data']['save_metadata']:
                    metadata = {
                        'leg': leg,
                        'wavelength_nm': wavelength,
                        'timestamp': datetime.now().isoformat(),
                        'fringes_visible': fringes_visible,
                        'fringe_metric': float(metric),
                        'laser_power_uw': self.config['hardware']['laser']['power_uw'],
                        'motor_angles': self.motors.angles.copy()
                    }
                    metadata_file = filepath.with_suffix('.yaml')
                    with open(metadata_file, 'w') as f:
                        yaml.dump(metadata, f)
                
                print(f"  💾 Saved: {filename}")
                self.collected_images.append(str(filepath))
        
        print("\n" + "=" * 60)
        print("DATA COLLECTION COMPLETE")
        print(f"Total images collected: {len(self.collected_images)}")
        print("=" * 60)
        
        # Save session summary
        self.session_metadata['session_end'] = datetime.now().isoformat()
        self.session_metadata['images_collected'] = self.collected_images
        
        summary_file = self.output_dir / 'session_summary.yaml'
        with open(summary_file, 'w') as f:
            yaml.dump(self.session_metadata, f)
        print(f"\nSession summary saved: {summary_file}")
    
    def run(self):
        """Run full data collection session"""
        try:
            self.connect_hardware()
            time.sleep(1)  # Brief pause before starting
            self.collect_data()
        except KeyboardInterrupt:
            print("\n\n⚠ Data collection interrupted by user")
        except Exception as e:
            print(f"\n\n✗ Error during data collection: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.disconnect_hardware()


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Automated Data Collection for Digital Holography'
    )
    parser.add_argument(
        '--config', 
        default='experiment_config.yaml',
        help='Path to configuration YAML file'
    )
    
    args = parser.parse_args()
    
    print("\n" + "=" * 60)
    print("DIGITAL HOLOGRAPHY DATA COLLECTOR")
    print("Photonic Lantern Testbed - UCF CREOL")
    print("=" * 60 + "\n")
    
    collector = HolographyDataCollector(config_file=args.config)
    collector.run()
    
    print("\n✓ Program finished.\n")


if __name__ == '__main__':
    main()
