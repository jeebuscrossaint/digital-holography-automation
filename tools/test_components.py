# -*- coding: utf-8 -*-
"""
Test & Example Scripts for Individual Hardware Components

Use these to test each piece of hardware independently before running
the full automation pipeline.

Author: Amarnath
Date: March 2026
"""

import sys
import time
import numpy as np
import matplotlib.pyplot as plt

# Add paths
sys.path.append(r'Code That Connects To Other Code\Code That Connects To Other Code')
sys.path.append(r'Code That Connects To Other Code\Code That Connects To Other Code\XenicsPython\Xenics')


def test_laser():
    """Test HP Tunable Laser connection and control"""
    print("\n" + "="*50)
    print("TESTING HP TUNABLE LASER")
    print("="*50)
    
    from HPTunableLaserSource import HPTunableLaserSource
    
    try:
        # Connect
        print("Connecting to laser...")
        laser = HPTunableLaserSource('GPIB0::24::INSTR')
        
        # Query current settings
        current_wavelength = laser.checkWavelength()
        current_power = laser.checkPowerAmplitude()
        power_unit = laser.checkPowerUnit()
        output_on = laser.isOutputOn()
        
        print(f"✓ Connected successfully")
        print(f"  Wavelength: {current_wavelength}")
        print(f"  Power: {current_power} {power_unit}")
        print(f"  Output: {'ON' if output_on else 'OFF'}")
        
        # Test wavelength sweep
        print("\nTesting wavelength sweep (1545, 1550, 1555 nm)...")
        for wl in [1545, 1550, 1555]:
            laser.changeWavelength(wl)
            time.sleep(0.5)
            actual = laser.checkWavelength()
            print(f"  Set {wl} nm → Actual: {actual}")
        
        # Test power adjustment
        print("\nTesting power adjustment...")
        laser.changePowerUnit('UW')
        laser.powerAmplitude(200)
        time.sleep(0.2)
        print(f"  Power set to 200 UW")
        
        print("\n✓ Laser test complete")
        return True
        
    except Exception as e:
        print(f"✗ Laser test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_camera():
    """Test Xenics Camera connection and image capture"""
    print("\n" + "="*50)
    print("TESTING XENICS CAMERA")
    print("Xenics Bobcat 320 GigE (via Ethernet-to-USB)")
    print("="*50)
    print("\nNOTE: If camera not found, see GIGE_CAMERA_SETUP.md")
    print("      Make sure network adapter has static IP 192.168.1.100")
    
    from XenicsCam import xCam, dev_discovery
    
    try:
        # Discover camera
        print("\nDiscovering cameras...")
        url = dev_discovery()
        
        # Connect
        print(f"Connecting to camera at {url}...")
        camera = xCam(url=url)
        
        print(f"✓ Connected successfully")
        print(f"  PID: {camera.pid}")
        print(f"  Serial: {camera.ser}")
        print(f"  Exposure: {camera.exposure_time}")
        
        # Capture test frame
        print("\nCapturing test frame...")
        frame = camera.getFrame()
        
        if frame is not None:
            print(f"✓ Frame captured: shape={frame.shape}, dtype={frame.dtype}")
            print(f"  Min: {np.min(frame)}, Max: {np.max(frame)}, Mean: {np.mean(frame):.1f}")
            
            # Display frame
            plt.figure(figsize=(8, 6))
            plt.imshow(frame, cmap='gray')
            plt.colorbar()
            plt.title('Test Frame from Xenics Camera')
            plt.show()
        else:
            print("✗ Failed to capture frame")
        
        # Cleanup
        camera.stopCapture()
        camera.closeCamera()
        
        print("\n✓ Camera test complete")
        return True
        
    except Exception as e:
        print(f"✗ Camera test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_fiber_switch():
    """Test Dicon Fiber Switch connection and switching"""
    print("\n" + "="*50)
    print("TESTING DICON FIBER SWITCH")
    print("="*50)
    
    from D700DiconSwitch import D700DiconSwitch, list_available_ports
    
    try:
        # List available ports
        print("Available serial ports:")
        list_available_ports()
        
        # Connect
        print("\nConnecting to switch on COM6...")
        switch = D700DiconSwitch(port='COM6')
        
        print("✓ Connected successfully")
        
        # Get current position
        current = switch.get_position(module=1)
        print(f"  Current position: {current}")
        
        # Test switching
        print("\nTesting switching between positions 1, 2, 3...")
        for pos in [1, 2, 3, 1]:
            print(f"  Moving to position {pos}...")
            switch.move_to_position(module=1, position=pos)
            time.sleep(1)
            actual = switch.get_position(module=1)
            check = "✓" if actual == pos else "✗"
            print(f"    {check} Position confirmed: {actual}")
        
        # Cleanup
        switch.close()
        
        print("\n✓ Fiber switch test complete")
        return True
        
    except Exception as e:
        print(f"✗ Fiber switch test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_polarization_motors():
    """Test Thorlabs Polarization Motors"""
    print("\n" + "="*50)
    print("TESTING POLARIZATION MOTORS")
    print("="*50)
    
    from polMotors import polMotors
    
    try:
        # Connect
        print("Connecting to motors (serial: 38394984)...")
        motors = polMotors(serialNumber=b"38394984")
        
        print("✓ Connected successfully")
        print(f"  Initial angles: {motors.angles}")
        
        # Test moving motors
        print("\nTesting motor movements...")
        test_angles = [
            [30, 0, 0],
            [30, 45, 0],
            [0, 45, 0],
            [0, 0, 0]
        ]
        
        for angles in test_angles:
            print(f"  Moving to {angles}...")
            for i, angle in enumerate(angles):
                if angle != motors.angles[i]:
                    motors.moveMotor(i+1, angle)
            
            # Wait for motion to complete
            while motors.isBusy():
                time.sleep(0.1)
            
            print(f"    ✓ Motors at {motors.angles}")
            time.sleep(0.5)
        
        print("\n✓ Polarization motors test complete")
        return True
        
    except Exception as e:
        print(f"✗ Motors test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_fringe_detection():
    """Test fringe detection algorithms"""
    print("\n" + "="*50)
    print("TESTING FRINGE DETECTION")
    print("="*50)
    
    from fringe_detection import (
        check_fringes_visible,
        calculate_variance,
        calculate_fringe_visibility_michelson,
        calculate_fft_peak_ratio
    )
    
    # Create synthetic test images
    size = 256
    x = np.linspace(-np.pi, np.pi, size)
    X, Y = np.meshgrid(x, x)
    
    # Image with good fringes
    fringes_good = 0.5 + 0.4 * np.cos(10*X + 5*Y)
    
    # Image with weak fringes
    fringes_weak = 0.5 + 0.1 * np.cos(10*X + 5*Y)
    
    # Image with no fringes (uniform)
    uniform = np.ones((size, size)) * 0.5
    
    test_images = [
        ("Good Fringes", fringes_good),
        ("Weak Fringes", fringes_weak),
        ("Uniform (No Fringes)", uniform)
    ]
    
    print("\nTesting detection on synthetic images...\n")
    
    for name, image in test_images:
        print(f"{name}:")
        
        # Test all methods
        visible_var, metric_var = check_fringes_visible(image, 'variance', 0.01)
        visible_mich, metric_mich = check_fringes_visible(image, 'michelson', 0.2)
        visible_fft, metric_fft = check_fringes_visible(image, 'fft_peaks', 0.01)
        
        print(f"  Variance:  {metric_var:.4f} → {'VISIBLE' if visible_var else 'NOT VISIBLE'}")
        print(f"  Michelson: {metric_mich:.4f} → {'VISIBLE' if visible_mich else 'NOT VISIBLE'}")
        print(f"  FFT Peaks: {metric_fft:.4f} → {'VISIBLE' if visible_fft else 'NOT VISIBLE'}")
        print()
    
    # Display images
    fig, axes = plt.subplots(1, 3, figsize=(12, 4))
    for ax, (name, image) in zip(axes, test_images):
        ax.imshow(image, cmap='gray')
        ax.set_title(name)
        ax.axis('off')
    plt.tight_layout()
    plt.show()
    
    print("✓ Fringe detection test complete")
    return True


def main():
    """Run all tests"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Test individual hardware components')
    parser.add_argument('--laser', action='store_true', help='Test laser')
    parser.add_argument('--camera', action='store_true', help='Test camera')
    parser.add_argument('--switch', action='store_true', help='Test fiber switch')
    parser.add_argument('--motors', action='store_true', help='Test polarization motors')
    parser.add_argument('--fringes', action='store_true', help='Test fringe detection')
    parser.add_argument('--all', action='store_true', help='Test all components')
    
    args = parser.parse_args()
    
    # If no specific test selected, show menu
    if not any([args.laser, args.camera, args.switch, args.motors, args.fringes, args.all]):
        print("\n" + "="*50)
        print("HARDWARE TESTING MENU")
        print("="*50)
        print("\nUsage:")
        print("  python test_components.py --laser     # Test laser")
        print("  python test_components.py --camera    # Test camera")
        print("  python test_components.py --switch    # Test fiber switch")
        print("  python test_components.py --motors    # Test motors")
        print("  python test_components.py --fringes   # Test fringe detection")
        print("  python test_components.py --all       # Test everything")
        print()
        return
    
    results = {}
    
    if args.all or args.laser:
        results['Laser'] = test_laser()
    
    if args.all or args.camera:
        results['Camera'] = test_camera()
    
    if args.all or args.switch:
        results['Fiber Switch'] = test_fiber_switch()
    
    if args.all or args.motors:
        results['Motors'] = test_polarization_motors()
    
    if args.all or args.fringes:
        results['Fringe Detection'] = test_fringe_detection()
    
    # Summary
    if results:
        print("\n" + "="*50)
        print("TEST SUMMARY")
        print("="*50)
        for component, passed in results.items():
            status = "✓ PASS" if passed else "✗ FAIL"
            print(f"  {component}: {status}")
        print()


if __name__ == '__main__':
    main()
