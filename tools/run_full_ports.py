"""Run the REAL software pipeline (HolographyDataProcessor) on 6port/7port.
Converts the 16-bit PNG holograms into the leg*.npy the software expects, then
runs process_dataset -> 8-panel per-leg analysis figures + .npz + summary yaml,
exactly as the PNG/npy software flow produces them."""
import sys, os, glob, re, copy
import numpy as np
import yaml
from PIL import Image

sys.path[:0] = ['.', 'lib']
from data_processing import HolographyDataProcessor

BASE = yaml.safe_load(open('experiment_config.yaml'))

for port in sys.argv[1:] or ['6port', '7port']:
    # 1. Convert each 16-bit PNG hologram -> legNN.npy (raw, no 8-bit clipping).
    for png in sorted(glob.glob(os.path.join(port, '*.png'))):
        n = int(re.search(r'leg(\d+)', os.path.basename(png)).group(1))
        H = np.asarray(Image.open(png), dtype=np.float64)   # mode I;16 -> raw values
        np.save(os.path.join(port, f'leg{n:02d}.npy'), H)

    # 2. Point a copy of the real config at this folder and run the real pipeline.
    cfg = copy.deepcopy(BASE)
    cfg['data']['output_dir'] = f'./{port}/'
    cfg_path = f'_config_{port}.yaml'
    with open(cfg_path, 'w') as f:
        yaml.dump(cfg, f)

    print('\n' + '#' * 60 + f'\n# {port}\n' + '#' * 60)
    proc = HolographyDataProcessor(config_file=cfg_path)
    proc.process_dataset(show_plots=False, save_plots=True)
