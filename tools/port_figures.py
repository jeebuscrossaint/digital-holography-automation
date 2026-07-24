"""Full analysis figures for the 6port/7port datasets.
Per leg: raw hologram | recovered |E| | recovered phase | reconstructed |E| | mode power.
Plus one fidelity-vs-leg summary per port. Saves PNGs to analysis_output/."""
import sys, os, glob
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image

sys.path[:0] = ['.', 'lib', 'tools']
from recon_dev import (recover_field, center_crop_on_beam, get_modes,
                       best_for, GRID, NUM_MODES)
from calebsUsefulFunctions import (normalizeIntensity, modeDecomp,
                                    combinedOutput, generatePhaseMask)

OUT = 'analysis_output'
os.makedirs(OUT, exist_ok=True)


def load_png(path):
    H = np.asarray(Image.open(path), dtype=float)   # 16-bit raw, NO convert('L')
    H = np.nan_to_num(H)
    s = min(H.shape)
    y0, x0 = (H.shape[0] - s) // 2, (H.shape[1] - s) // 2
    return H[y0:y0 + s, x0:x0 + s]


def analyze(H):
    fid, p = best_for(H)                             # sweep -> best params
    ES = recover_field(H, lp_cut=p['lp'])
    fld = normalizeIntensity(center_crop_on_beam(ES, GRID))
    fld = normalizeIntensity(fld * generatePhaseMask(GRID, p['phase']))
    modes = get_modes(p['fov'])
    dec = modeDecomp(fld, modes, p['nm'])
    rec = combinedOutput(modes[:p['nm']], dec)
    power = np.abs(dec) ** 2
    return fid, p, fld, rec, power


def leg_figure(name, H, fid, p, fld, rec, power):
    fig, ax = plt.subplots(1, 5, figsize=(18, 3.6))
    ax[0].imshow(H, cmap='gray');            ax[0].set_title(f'{name}\nraw hologram (16-bit)')
    ax[1].imshow(np.abs(fld), cmap='viridis'); ax[1].set_title('recovered |E|')
    ax[2].imshow(np.angle(fld), cmap='twilight'); ax[2].set_title('recovered phase')
    ax[3].imshow(np.abs(rec), cmap='viridis'); ax[3].set_title(f'reconstructed |E|\nfidelity={fid:.3f}')
    ax[4].bar(range(len(power)), power / power.sum()); ax[4].set_title('mode power')
    ax[4].set_xlabel('LP mode #'); ax[4].set_ylabel('frac. power')
    for a in ax[:4]:
        a.set_xticks([]); a.set_yticks([])
    fig.tight_layout()
    out = os.path.join(OUT, f'{name}_analysis.png')
    fig.savefig(out, dpi=110); plt.close(fig)
    return out


summary = {}
for folder in sys.argv[1:] or ['6port', '7port']:
    fids, labels = [], []
    for f in sorted(glob.glob(os.path.join(folder, '*.png'))):
        name = os.path.splitext(os.path.basename(f))[0]
        H = load_png(f)
        fid, p, fld, rec, power = analyze(H)
        out = leg_figure(name, H, fid, p, fld, rec, power)
        fids.append(fid); labels.append(name.replace(folder, 'leg'))
        print(f'{name}: fidelity={fid:.3f} -> {out}')
    # summary bar chart for this port
    fig, ax = plt.subplots(figsize=(7, 4))
    bars = ax.bar(labels, fids, color=['#c0392b' if v < 0.7 else '#2980b9' for v in fids])
    ax.axhline(np.mean(fids), ls='--', color='k', lw=1,
               label=f'mean={np.mean(fids):.3f}')
    ax.set_ylim(0, 1); ax.set_ylabel('fidelity |<E_rec,E_S>|^2')
    ax.set_title(f'{folder}: reconstruction fidelity per leg'); ax.legend()
    for b, v in zip(bars, fids):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.01, f'{v:.2f}', ha='center', fontsize=8)
    fig.tight_layout()
    sp = os.path.join(OUT, f'{folder}_fidelity_summary.png')
    fig.savefig(sp, dpi=120); plt.close(fig)
    summary[folder] = (np.mean(fids), sp)
    print(f'{folder}: mean fidelity={np.mean(fids):.3f} -> {sp}\n')

print('SUMMARY:', {k: round(v[0], 3) for k, v in summary.items()})
