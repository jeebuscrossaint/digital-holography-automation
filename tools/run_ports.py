"""Run the recon_dev fidelity sweep on the 6port/7port PNG holograms."""
import sys, os, glob
import numpy as np
from PIL import Image

sys.path[:0] = ['.', 'lib', 'tools']
from recon_dev import best_for


def load_png(path):
    # 16-bit camera holograms (mode I;16). Read RAW — do NOT convert('L'),
    # which clips to 8-bit and saturates every pixel to 255.
    H = np.asarray(Image.open(path), dtype=float)
    H = np.nan_to_num(H)                         # camera dead pixels -> 0
    s = min(H.shape)                             # center square crop for the FFT recon
    y0 = (H.shape[0] - s) // 2
    x0 = (H.shape[1] - s) // 2
    return H[y0:y0 + s, x0:x0 + s]


for folder in sys.argv[1:] or ['6port', '7port']:
    print(f'\n=== {folder} ===')
    for f in sorted(glob.glob(os.path.join(folder, '*.png'))):
        H = load_png(f)
        try:
            fid, params = best_for(H)
            print(f'{os.path.basename(f)}: shape={H.shape} range={H.min():.0f}-{H.max():.0f} '
                  f'fidelity={fid}  {params}')
        except Exception as e:
            print(f'{os.path.basename(f)}: shape={H.shape} range={H.min():.0f}-{H.max():.0f} '
                  f'FAILED -> {type(e).__name__}: {e}')
