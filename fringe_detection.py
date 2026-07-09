# -*- coding: utf-8 -*-
"""
Fringe Visibility Detection for Digital Holography
Used to determine if interference fringes are visible in camera images
"""

import os
import sys
import numpy as np
import matplotlib.pyplot as plt


def _caleb_funcs():
    """Lazily import Caleb's FFT helpers from lib/ so the optimizer's notion
    of 'good fringes' matches the reconstruction pipeline exactly."""
    lib = os.path.join(os.path.dirname(__file__), "lib")
    if os.path.isdir(lib) and lib not in sys.path:
        sys.path.insert(0, lib)
    from calebsUsefulFunctions import (filterForQuadrant, filterDCComponents,
                                        getBlurredCentroid, getMaxIndex)
    return filterForQuadrant, filterDCComponents, getBlurredCentroid, getMaxIndex


def _center_crop_square(image):
    """Center-crop to a square. Caleb's filterDCComponents assumes a square
    frame (it indexes both axes with shape[0] and builds a square DC mask),
    but the Bobcat 320 is 320x256 — so crop before using his helpers."""
    img = np.asarray(image)
    h, w = img.shape[:2]
    s = min(h, w)
    y0 = (h - s) // 2
    x0 = (w - s) // 2
    return img[y0:y0 + s, x0:x0 + s]


def calculate_sideband_energy(image, quadrant=None, line_filter_width=5,
                              dc_diameter=40, window=4):
    """Carrier-to-background prominence of the off-axis fringe sideband — the
    fringe-quality metric the optimizer maximizes.

    FFT the (square-cropped) image, zero the DC cross + center disk (Caleb's
    filter), find the brightest remaining point (the interference carrier,
    which sits at one fixed off-axis spatial frequency), and return the
    carrier's average power divided by the average background power elsewhere.

    This is an SNR-like ratio: empirically ~600–13000 for clear fringes vs
    ~40 for noise (a >100x separation), and scale-invariant. Normalizing by
    the BACKGROUND rather than by DC is what gives the separation — the bright
    beam envelope dominates DC and otherwise swamps the carrier (that made
    even gorgeous fringes read ~0.004 and never clear the threshold).

    quadrant: None (default) finds the carrier anywhere off-DC, so it works
    regardless of which diagonal the tilt puts it in. Pass 1/2/3/4 to restrict
    to one corner (Caleb's original 2/4 only works for one tilt direction)."""
    filter_for_quadrant, filter_dc, blurred_centroid, max_index = _caleb_funcs()
    img = _center_crop_square(np.asarray(image, dtype=float))
    power = np.abs(np.fft.fftshift(np.fft.fft2(img))) ** 2

    side = filter_for_quadrant(power, quadrant) if quadrant else power.copy()
    side = filter_dc(side, line_filter_width, dc_diameter)  # kill DC cross+disk

    # Locate the carrier the verified way (Caleb's tutorial): disk-blur, then
    # take the max of the blurred spectrum. A raw argmax on the un-blurred power
    # can latch onto a single noise / hot-pixel spike instead of the carrier.
    _, conv, _ = blurred_centroid(side, 2 * window + 1)
    py, px = max_index(conv)
    y0, y1 = max(0, py - window), min(side.shape[0], py + window + 1)
    x0, x1 = max(0, px - window), min(side.shape[1], px + window + 1)
    peak_mean = float(side[y0:y1, x0:x1].mean())

    # Background = off-DC power well away from the carrier.
    bg = side.copy()
    m = 3 * window
    bg[max(0, py - m):py + m + 1, max(0, px - m):px + m + 1] = 0
    vals = bg[bg > 0]
    bg_mean = float(vals.mean()) if vals.size else 1.0
    return peak_mean / (bg_mean + 1e-12)


def calculate_sideband_balance(image):
    """Dual-polarization balance metric — the WEAKER of the two twin pairs.

    A dual-polarization off-axis hologram has TWO carriers (one per reference
    beam, at different tilt angles), so the FFT shows two twin pairs on the two
    diagonals: one polarization's pair in UL/LR, the other's in UR/LL.
    `calculate_sideband_energy(quadrant=1)` measures the UL pair's prominence
    (polarization A), `quadrant=2` the UR pair's (polarization B).

    Returning the MINIMUM of the two is the key: an optimizer that maximizes
    this is forced to bring the WEAKER axis up — i.e. it BALANCES both
    polarizations, instead of the plain `sideband` metric which just cranks the
    single brightest peak and leaves one axis dead. Use method='balance' in the
    polarization optimizer for a dual-pol lantern.

    Returns (weaker, polA, polB) so callers can log the split / imbalance ratio.
    """
    a = calculate_sideband_energy(image, quadrant=1)   # UL  -> polarization A
    b = calculate_sideband_energy(image, quadrant=2)   # UR  -> polarization B
    return min(a, b), a, b


def diagnose_fringe_metrics(image):
    """Compute every candidate metric on one frame so they can be compared
    empirically at the rig — turn the paddles and watch which one tracks
    fringe contrast most cleanly / monotonically. Returns a dict."""
    out = {
        "variance":          calculate_variance(image),
        "michelson":         calculate_fringe_visibility_michelson(image),
        "fft_peak_ratio":    calculate_fft_peak_ratio(image),
    }
    try:
        out["sideband"] = calculate_sideband_energy(image)   # carrier prominence (recommended)
    except Exception as e:
        out["sideband_error"] = str(e)
    try:
        weaker, a, b = calculate_sideband_balance(image)     # dual-pol: weaker axis
        out["balance"] = weaker
        out["polA"], out["polB"] = a, b
    except Exception as e:
        out["balance_error"] = str(e)
    return out


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


def check_saturation(image, sat_level=65535, sat_fraction_max=0.001,
                     near_full=0.97):
    """Detect sensor saturation/clipping, which invalidates a hologram.

    When fringe peaks exceed the ADC full scale they clip — the recorded
    intensity is no longer linear in the optical field, so the clipped
    sinusoid dumps spurious harmonics into Fourier space and corrupts the
    sideband. The reconstructed amplitude AND phase are then wrong. Reject
    such frames (or reduce exposure / laser power).

    Args:
        image: 2D camera frame (raw counts)
        sat_level: ADC full scale (Bobcat 320 is Mono16 -> 65535)
        sat_fraction_max: max tolerated fraction of saturated pixels
        near_full: count pixels >= near_full*sat_level as saturated, to catch
                   clipping that lands just under the ceiling after NUC

    Returns:
        dict: {saturated, fraction, n_saturated, max_value, fill_fraction}
              `saturated` True => data should be considered invalid.
    """
    arr = np.asarray(image)
    sat_thresh = near_full * sat_level
    n_sat = int(np.count_nonzero(arr >= sat_thresh))
    frac = n_sat / arr.size if arr.size else 0.0
    mx = int(arr.max()) if arr.size else 0
    return {
        "saturated": frac > sat_fraction_max,
        "fraction": frac,
        "n_saturated": n_sat,
        "max_value": mx,
        "fill_fraction": mx / sat_level if sat_level else 0.0,
    }


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

    elif method == 'sideband':
        metric = calculate_sideband_energy(image)
        visible = metric > threshold

    elif method == 'balance':
        # Dual-pol: optimize the WEAKER twin pair so both axes come up together.
        metric = calculate_sideband_balance(image)[0]
        visible = metric > threshold

    else:
        raise ValueError(f"Unknown method: {method}")
    
    return visible, metric


def optimize_polarization_for_fringes(camera, pol_motors, max_attempts=60,
                                      method='sideband', threshold=0.15,
                                      angle_step=20, paddles=(1, 2, 3),
                                      max_travel=160.0, settle_s=0.2,
                                      diagnostics=True):
    """Maximize fringe visibility by coordinate-ascent over the paddle angles.

    For each paddle in turn, scan its full travel, move it to the best angle,
    then move to the next paddle (holding the others) — then a finer pass.
    This uses ALL THREE paddles and spends the frame budget across them,
    fixing the old bug where itertools.product truncation meant paddle 1
    never moved off 0.

    Args:
        camera, pol_motors: hardware handles
        max_attempts: frame budget (each frame = one measurement)
        method: fringe metric (default 'sideband' = carrier-locked FFT)
        threshold: success cutoff on the metric (tune from the live values)
        angle_step: coarse step (deg); a finer half-step pass follows
        paddles: which paddles to optimize (default all three)
        max_travel: paddle range in degrees
        settle_s: extra settle time after each move
        diagnostics: if True, log every candidate metric per frame so the
                     best metric can be chosen empirically at the rig

    Returns:
        (success, best_metric, best_angles[3])
    """
    import time

    def settle():
        try:
            while pol_motors.isBusy():
                time.sleep(0.05)
        except Exception:
            pass
        time.sleep(settle_s)

    def measure():
        settle()
        frame = camera.getFrame()
        if frame is None:
            return None
        if diagnostics:
            try:
                d = diagnose_fringe_metrics(frame)
                print("    metrics: " + "  ".join(
                    f"{k}={v:.4f}" for k, v in d.items()
                    if isinstance(v, (int, float))))
            except Exception:
                pass
        _, m = check_fringes_visible(frame, method, threshold)
        return m

    # Start from where the paddles already are.
    current = {}
    for p in paddles:
        try:
            current[p] = float(pol_motors.getPosition(p))
        except Exception:
            current[p] = 0.0

    best_metric = -np.inf
    attempts = 0
    stop = False

    for step in (angle_step, max(angle_step // 2, 5)):   # coarse, then fine
        grid = np.arange(0.0, max_travel + 1e-9, step)
        for p in paddles:
            local_best_ang = current[p]
            local_best_metric = best_metric
            for ang in grid:
                if attempts >= max_attempts:
                    stop = True
                    break
                pol_motors.moveMotor(p, float(ang))
                m = measure()
                attempts += 1
                if m is None:
                    continue
                print(f"  Attempt {attempts}: paddle {p} @ {ang:.0f}° "
                      f"-> {method}={m:.4f}")
                if m > local_best_metric:
                    local_best_metric = m
                    local_best_ang = float(ang)
            # Lock this paddle at its best before moving to the next.
            current[p] = local_best_ang
            pol_motors.moveMotor(p, local_best_ang)
            if local_best_metric > best_metric:
                best_metric = local_best_metric
            if stop:
                break
        if stop or best_metric >= threshold:
            break

    # Leave every paddle at its best-found angle.
    for p in paddles:
        pol_motors.moveMotor(p, current[p])
    settle()

    best_angles = [round(current.get(i, 0.0), 1) for i in (1, 2, 3)]
    if best_metric == -np.inf:
        best_metric = 0.0
    success = best_metric >= threshold
    print(f"  Best: paddles={best_angles}, {method}={best_metric:.4f}, "
          f"success={success} ({attempts} frames)")
    return success, float(best_metric), best_angles


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
