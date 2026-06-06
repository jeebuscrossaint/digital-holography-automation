# -*- coding: utf-8 -*-
"""Results tab — table of processed holograms (fidelity + mode powers)."""

import os
from pathlib import Path

from PySide6.QtWidgets import (
    QHBoxLayout, QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)


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

        self._results_tree = QTreeWidget()
        self._results_tree.setColumnCount(3)
        self._results_tree.setHeaderLabels(["Hologram", "Fidelity", "Mode powers (LP01 → LP06)"])
        self._results_tree.setColumnWidth(0, 240)
        self._results_tree.setColumnWidth(1, 90)
        self._results_tree.setColumnWidth(2, 400)
        lay.addWidget(self._results_tree, 1)

        self.tabs.addTab(tab, "Results")

    def _open_data_folder(self):
        d = Path(self.config.get("data", {}).get("output_dir", "./holography_data"))
        d.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(d.absolute()))
        except Exception as e:
            self._log(f"Could not open folder: {e}", "WARN")

    def _refresh_results(self):
        import yaml
        self._results_tree.clear()
        try:
            data_dir     = Path(self.config.get("data", {}).get("output_dir", "./holography_data"))
            summary_file = data_dir / "processed_results" / "processing_summary.yaml"
            if not summary_file.exists():
                return
            with open(summary_file) as f:
                summary = yaml.safe_load(f) or {}
            for res in summary.get("results", []):
                powers = res.get("mode_powers", [])
                pstr   = "  ".join(f"{p*100:.1f}%" for p in powers[:6])
                QTreeWidgetItem(self._results_tree, [
                    res.get("filename", ""),
                    f"{res.get('fidelity', 0):.4f}",
                    pstr,
                ])
        except Exception:
            pass
