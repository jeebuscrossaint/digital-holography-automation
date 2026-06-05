# Reference — instrument-control notebooks

Jupyter notebooks for talking to various lab instruments over VISA/serial,
kept here purely as **reference material**. None of this is imported or used by
the application — the shipping app's drivers live in `hardware/`.

Courtesy of David (lab notebooks for the wider bench).

| Notebook | Instrument | Relevance |
|---|---|---|
| `hp8168de_tunable_laser (1).ipynb` | HP 8168D/E tunable laser | Same laser family as ours — handy as a SCPI reference; our working driver is `hardware/HPTunableLaserSource.py` |
| `aq6370c_optical_spectrum_analyzer.ipynb` | Yokogawa AQ6370C OSA | Not in the current setup |
| `hp8563e_spectrum_analyzer.ipynb` | HP 8563E spectrum analyzer | Not in the current setup |
| `rigol_mho5104_oscilloscope.ipynb` | Rigol MHO5104 scope | Not in the current setup |
| `wbsg2_function_generator.ipynb` | WBSG2 function generator | Not in the current setup |

If you wire up one of these instruments later, start from its notebook and port
the logic into a driver under `hardware/` (matching the style of the existing
drivers so the GUI can use it).
