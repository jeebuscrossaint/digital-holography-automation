"""
Check what properties the Xenics camera actually has
"""
import sys
import os

# Add Caleb's code paths
sys.path.insert(0, os.path.join(os.getcwd(), 'Code That Connects To Other Code', 'Code That Connects To Other Code'))
sys.path.insert(0, os.path.join(os.getcwd(), 'Code That Connects To Other Code', 'Code That Connects To Other Code', 'XenicsPython', 'Xenics'))

from xenics.xeneth import enumerate_devices, XCamera

# Discover devices
print("Discovering Xenics cameras...")
devices = enumerate_devices()

for i, dev in enumerate(devices):
    print(f"\nDevice {i}:")
    print(f"  Name: {dev.name}")
    print(f"  URL: {dev.url}")
    print(f"  Serial: {dev.serial}")
    print(f"  PID: {dev.pid}")
    print(f"  State: {dev.state}")
    
    try:
        print(f"\n  Opening camera...")
        cam = XCamera(dev.url)
        
        print(f"\n  Available properties:")
        for prop_name in sorted(cam.props.keys()):
            try:
                value = cam.props[prop_name].get()
                print(f"    {prop_name}: {value}")
            except:
                print(f"    {prop_name}: <error reading>")
        
        cam.close()
        break
        
    except Exception as e:
        print(f"  Error opening camera: {e}")
