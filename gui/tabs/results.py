# -*- coding: utf-8 -*-
"""Results tab — per-hologram fidelity + mode powers, color-coded so bad
frames stand out, with double-click to open each frame's full analysis panel."""

import os
from pathlib import Path

from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from ..style import ACCENT_GREEN, ACCENT_AMBER, ACCENT_RED


class ResultsTabMixin:
    def _build_results_tab(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(14, 14, 14, 14)

        btns = QHBoxLayout()
        open_btn = QPushButton("Open data folder"); open_btn.clicked.connect(self._open_data_folder)
        refresh = QPushButton("Refresh"); refresh.clicked.connect(self._refresh_results)
        btns.addWidget(open_btn); btns.addWidget(refresh); btns.addStretch(1)
        lay.addLayout(btns)

        self._results_summary = QLabel("No results yet — run Process or Full.")
        self._results_summary.setObjectName("Section")
        lay.addWidget(self._results_summary)

        self._results_tree = QTreeWidget()
        self._results_tree.setColumnCount(4)
        self._results_tree.setHeaderLabels(
            ["Hologram", "λ (nm)", "Fidelity", "Mode powers (LP01 → LP06)"])
        self._results_tree.setColumnWidth(0, 230)
        self._results_tree.setColumnWidth(1, 70)
        self._results_tree.setColumnWidth(2, 90)
        self._results_tree.setColumnWidth(3, 420)
        self._results_tree.setRootIsDecorated(False)
        self._results_tree.setAlternatingRowColors(True)
        self._results_tree.itemDoubleClicked.connect(self._open_result_panel)
        lay.addWidget(self._results_tree, 1)

        hint = QLabel("Double-click a row to open its full analysis panel "
                      "(hologram · FFT · recovered field · mode decomposition).")
        hint.setObjectName("Small")
        lay.addWidget(hint)

        self.tabs.addTab(tab, "Results")

    def _open_data_folder(self):
        d = Path(self.config.get("data", {}).get("output_dir", "./holography_data"))
        d.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(d.absolute()))
        except Exception as e:
            self._log(f"Could not open folder: {e}", "WARN")

    @staticmethod
    def _fidelity_color(fid: float) -> str:
        if fid >= 0.85:
            return ACCENT_GREEN          # good
        if fid >= 0.50:
            return ACCENT_AMBER          # weak — look at it
        return ACCENT_RED                # failed reconstruction

    def _refresh_results(self):
        import yaml
        self._results_tree.clear()
        data_dir = Path(self.config.get("data", {}).get("output_dir", "./holography_data"))
        summary_file = data_dir / "processed_results" / "processing_summary.yaml"
        if not summary_file.exists():
            self._results_summary.setText("No results yet — run Process or Full.")
            return
        try:
            with open(summary_file) as f:
                summary = yaml.safe_load(f) or {}
        except Exception:
            self._results_summary.setText("Couldn't read results summary.")
            return

        rows = summary.get("results", [])
        fids = []
        # sort by wavelength when present, else filename
        rows = sorted(rows, key=lambda r: (r.get("wavelength_nm", 0), r.get("filename", "")))
        for res in rows:
            fid = float(res.get("fidelity", 0.0))
            wl = res.get("wavelength_nm", "")
            powers = res.get("mode_powers", [])
            pstr = "  ".join(f"{p*100:.1f}%" for p in powers[:6])
            item = QTreeWidgetItem(self._results_tree, [
                res.get("filename", ""), str(wl), f"{fid*100:.1f}%", pstr])
            item.setForeground(2, QBrush(QColor(self._fidelity_color(fid))))
            fids.append(fid)

        if fids:
            mean = sum(fids) / len(fids)
            bad = sum(1 for f in fids if f < 0.5)
            txt = (f"{len(fids)} holograms   ·   mean fidelity {mean*100:.1f}%   ·   "
                   f"range {min(fids)*100:.1f}–{max(fids)*100:.1f}%")
            if bad:
                txt += f"   ·   ⚠ {bad} failed (<50%) — re-capture"
            self._results_summary.setText(txt)
        else:
            self._results_summary.setText("No results yet — run Process or Full.")

    def _open_result_panel(self, item, _col):
        """Double-click a row -> open that frame's saved analysis panel."""
        fn = item.text(0)
        if not fn:
            return
        stem = fn.rsplit(".", 1)[0]
        data_dir = Path(self.config.get("data", {}).get("output_dir", "./holography_data"))
        png = data_dir / "processed_results" / f"{stem}_analysis.png"
        if png.exists():
            try:
                os.startfile(str(png.absolute()))
            except Exception as e:
                self._log(f"Couldn't open panel: {e}", "WARN")
        else:
            self._log(f"No analysis panel for {fn} yet — run Process/Full to generate it.",
                      "WARN")
