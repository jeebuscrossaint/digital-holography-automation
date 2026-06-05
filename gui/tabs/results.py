# -*- coding: utf-8 -*-
"""Results tab — table of processed holograms (fidelity + mode powers)."""

import os
from pathlib import Path
from tkinter import ttk


class ResultsTabMixin:
    def _build_results_tab(self):
        tab = ttk.Frame(self.notebook, padding=14)
        self.notebook.add(tab, text="Results")

        btn_row = ttk.Frame(tab)
        btn_row.pack(fill="x", pady=(0, 10))
        ttk.Button(btn_row, text="Open data folder",
                   command=self._open_data_folder).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row, text="Refresh",
                   command=self._refresh_results).pack(side="left")

        body = ttk.Frame(tab)
        body.pack(fill="both", expand=True)

        cols = ("file", "fidelity", "mode_powers")
        self._results_tree = ttk.Treeview(body, columns=cols, show="headings", height=24)
        self._results_tree.heading("file",        text="Hologram")
        self._results_tree.heading("fidelity",    text="Fidelity")
        self._results_tree.heading("mode_powers", text="Mode powers (LP01 → LP06)")
        self._results_tree.column("file",        width=240)
        self._results_tree.column("fidelity",    width=90, anchor="e")
        self._results_tree.column("mode_powers", width=400)

        vsb = ttk.Scrollbar(body, orient="vertical", command=self._results_tree.yview)
        self._results_tree.configure(yscrollcommand=vsb.set)
        self._results_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

    def _open_data_folder(self):
        d = Path(self.config.get("data", {}).get("output_dir", "./holography_data"))
        d.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(d.absolute()))
        except Exception as e:
            self._log(f"Could not open folder: {e}", "WARN")

    def _refresh_results(self):
        import yaml
        self._results_tree.delete(*self._results_tree.get_children())
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
                self._results_tree.insert("", "end", values=(
                    res.get("filename", ""),
                    f"{res.get('fidelity', 0):.4f}",
                    pstr,
                ))
        except Exception:
            pass
