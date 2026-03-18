# -*- coding: utf-8 -*-
"""
Fringe Visibility Detection for Digital Holography
Used to determine if interference fringes are visible in camera images
"""

import numpy as np
import matplotlib.pyplot as plt


def calculate_variance(image):
    """Calculate normalized variance of image intensity
    
    High variance indicates presence of fringes.
    Low variance indicates uniform illumination (no fringes).
    
    Args:
        image: 2D numpy array of image intensity
        
    Returns:
        Normalized variance (float)
    """
    mean_val = np.mean(image)
    if mean_val == 0:
        return 0
    variance = np.var(image)
    # Normalize by mean to get contrast metric
    normalized_var = variance / (mean_val ** 2)
    return normalized_var


def calculate_fringe_visibility_michelson(image):
    """Calculate fringe visibility using Michelson contrast
    
    V = (I_max - I_min) / (I_max + I_min)
    
    Args:
        image: 2D numpy array
        
    Returns:
        Visibility metric between 0 and 1
    """
    I_max = np.max(image)
    I_min = np.min(image)
    
    if (I_max + I_min) == 0:
        return 0
    
    visibility = (I_max - I_min) / (I_max + I_min)
    return visibility


def calculate_fft_peak_ratio(image):
    """Detect fringes by looking for peaks in FFT spectrum
    
    Fringes create distinct peaks in Fourier space (twin images).
    Compare peak intensity to DC component.
    
    Args:
        image: 2D numpy array
        
    Returns:
        Ratio of off-axis peak to DC (higher = better fringes)
    """
    # Compute FFT
    fft_image = np.fft.fftshift(np.fft.fft2(image))
    fft_power = np.abs(fft_image) ** 2
    
    # Find DC component (center)
    center = np.array(fft_power.shape) // 2
    dc_size = 20  # pixels to mask out around DC
    
    # Mask out DC component
    y, x = np.ogrid[:fft_power.shape[0], :fft_power.shape[1]]
    mask = (x - center[1])**2 + (y - center[0])**2 > dc_size**2
    fft_power_masked = fft_power * mask
    
    # Find peak in masked FFT
    peak_value = np.max(fft_power_masked)
    dc_value = fft_power[center[0], center[1]]
    
    if dc_value == 0:
        return 0
    
    ratio = peak_value / dc_value
    return ratio


def check_fringes_visible(image, method='variance', threshold=0.15):
    """Check if interference fringes are visible in image
    
    Args:
        image: 2D numpy array of camera image
        method: Detection method ('variance', 'michelson', or 'fft_peaks')
        threshold: Minimum value to consider fringes visible
        
    Returns:
        (bool, float): (fringes_visible, metric_value)
    """
    if method == 'variance':
        metric = calculate_variance(image)
        visible = metric > threshold
        
    elif method == 'michelson':
        metric = calculate_fringe_visibility_michelson(image)
        visible = metric > threshold
        
    elif method == 'fft_peaks':
        metric = calculate_fft_peak_ratio(image)
        # FFT ratio threshold should be higher (typically > 0.01)
        visible = metric > max(threshold, 0.01)
        
    else:
        raise ValueError(f"Unknown method: {method}")
    
    return visible, metric


def optimize_polarization_for_fringes(camera, pol_motors, max_attempts=10, 
                                     method='variance', threshold=0.15,
                                     angle_step=15):
    """Automatically adjust polarization to maximize fringe visibility
    
    Uses a simple grid search over polarization motor angles.
    
    Args:
        camera: XenicsCam instance
        pol_motors: polMotors instance  
        max_attempts: Maximum number of configurations to try
        method: Fringe detection method
        threshold: Target visibility threshold
        angle_step: Step size in degrees for motor adjustments
        
    Returns:
        (success, best_metric, best_angles)
    """
    import itertools
    import time
    
    # Try different combinations of motor positions
    # Focus on motor 1 and 2 (motor 3 less critical usually)
    angles_to_try = np.arange(0, 160, angle_step)
    
    best_metric = 0
    best_angles = [0, 0, 0]
    
    attempt = 0
    # Try different combinations (limited to max_attempts)
    for angle1, angle2 in itertools.product(angles_to_try[:4], angles_to_try[:4]):
        if attempt >= max_attempts:
            break
            
        # Move motors
        pol_motors.moveMotor(1, angle1)
        pol_motors.moveMotor(2, angle2)
        
        # Wait for motors to settle
        while pol_motors.isBusy():
            time.sleep(0.05)
        time.sleep(0.2)  # Additional settling
        
        # Capture frame
        frame = camera.getFrame()
        if frame is None:
            continue
        
        # Check fringe visibility
        visible, metric = check_fringes_visible(frame, method, threshold)
        
        print(f"  Attempt {attempt+1}: Motors=[{angle1:.0f}, {angle2:.0f}, 0] -> Metric={metric:.3f}")
        
        if metric > best_metric:
            best_metric = metric
            best_angles = [angle1, angle2, 0]
        
        if visible:
            print(f"  ✓ Fringes visible! Metric={metric:.3f}")
            return True, metric, best_angles
        
        attempt += 1
    
    # If we didn't find good fringes, return best attempt
    if best_metric > 0:
        print(f"  Best configuration: Motors={best_angles}, Metric={best_metric:.3f}")
        # Set motors to best found position
        pol_motors.moveMotor(1, best_angles[0])
        pol_motors.moveMotor(2, best_angles[1])
        while pol_motors.isBusy():
            time.sleep(0.05)
    
    return best_metric >= threshold, best_metric, best_angles


if __name__ == '__main__':
    # Test fringe detection on synthetic data
    print("Testing fringe detection algorithms...\n")
    
    # Create synthetic images
    size = 256
    x = np.linspace(-np.pi, np.pi, size)
    X, Y = np.meshgrid(x, x)
    
    # Image with fringes
    fringes = 0.5 + 0.4 * np.cos(10*X + 5*Y)
    
    # Uniform image (no fringes)
    uniform = np.ones((size, size)) * 0.5
    
    # Test both images
    for name, image in [("Fringes", fringes), ("Uniform", uniform)]:
        print(f"{name} image:")
        visible_var, metric_var = check_fringes_visible(image, 'variance', 0.01)
        visible_mich, metric_mich = check_fringes_visible(image, 'michelson', 0.2)
        visible_fft, metric_fft = check_fringes_visible(image, 'fft_peaks', 0.01)
        
        print(f"  Variance method: {metric_var:.4f} -> {visible_var}")
        print(f"  Michelson method: {metric_mich:.4f} -> {visible_mich}")
        print(f"  FFT peaks method: {metric_fft:.4f} -> {visible_fft}")
        print()
