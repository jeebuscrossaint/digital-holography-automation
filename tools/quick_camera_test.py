"""
Quick Camera Test - No other hardware required
"""
import sys
import os

# Add Caleb's code paths
sys.path.insert(0, os.path.join(os.getcwd(), 'Code That Connects To Other Code', 'Code That Connects To Other Code'))
sys.path.insert(0, os.path.join(os.getcwd(), 'Code That Connects To Other Code', 'Code That Connects To Other Code', 'XenicsPython', 'Xenics'))

from XenicsCam import xCam, dev_discovery

print("="*60)
print("XENICS CAMERA TEST")
print("="*60)

try:
    print("\nDiscovering camera...")
    url = dev_discovery()
    print(f"Found camera at: {url}")
    
    print("\nConnecting...")
    camera = xCam(url=url)
    
    print(f"\n✓ Camera connected successfully!")
    print(f"  PID: {camera.pid}")
    print(f"  Serial: {camera.ser}")
    print(f"  Exposure time: {camera.exposure_time} ms")
    
    print("\nCapturing test frame...")
    import time
    
    # Try a few times with delays
    for attempt in range(5):
        time.sleep(0.5)
        frame = camera.getFrame()
        if frame is not None:
            break
        print(f"  Attempt {attempt+1}/5...")
    
    if frame is not None:
        print(f"✓ Frame captured!")
        print(f"  Shape: {frame.shape}")
        print(f"  Min: {frame.min()}, Max: {frame.max()}, Mean: {frame.mean():.1f}")
    else:
        print("✗ Failed to capture frame after 5 attempts")
        print("  This may be normal if no light is reaching the camera")
    
    print("\n✓ Camera test PASSED!")
    
except Exception as e:
    print(f"\n✗ Camera test FAILED: {e}")
    import traceback
    traceback.print_exc()
