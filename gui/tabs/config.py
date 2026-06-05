# -*- coding: utf-8 -*-
"""Configuration tab — a scrollable editor over experiment_config.yaml."""

import tkinter as tk
from tkinter import ttk, messagebox

from ..runtime import CONFIG_FILE


class ConfigTabMixin:
    def _build_config_tab(self):
        tab = ttk.Frame(self.notebook, padding=(2, 4))
        self.notebook.add(tab, text="Configuration")

        # Scrollable container — Canvas + inner Frame
        outer = tk.Canvas(tab, highlightthickness=0, background="#1c1c1c")
        vsb   = ttk.Scrollbar(tab, orient="vertical", command=outer.yview)
        outer.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        outer.pack(side="left", fill="both", expand=True)

        inner = ttk.Frame(outer, padding=14)
        inner.bind("<Configure>",
                   lambda e: outer.configure(scrollregion=outer.bbox("all")))
        outer.create_window((0, 0), window=inner, anchor="nw")

        self._cfg_vars: dict = {}

        def section(title: str, pad_top: int = 14):
            ttk.Label(inner, text=title, font=self._font_section).pack(
                anchor="w", pady=(pad_top, 6))

        def field(label: str, key: str, default):
            row = ttk.Frame(inner)
            row.pack(fill="x", pady=3)
            ttk.Label(row, text=label, width=32, anchor="w",
                      font=self._font_body).pack(side="left")
            var = tk.StringVar(value=str(default))
            ttk.Entry(row, textvariable=var, width=44).pack(side="left", padx=6)
            self._cfg_vars[key] = var

        hw  = self.config.get("hardware", {})
        exp = self.config.get("experiment", {})

        section("Hardware", pad_top=0)
        field("Laser GPIB address",          "hardware.laser.gpib_address",
              hw.get("laser", {}).get("gpib_address", "GPIB0::24::INSTR"))
        field("Laser power (µW)",            "hardware.laser.power_uw",
              hw.get("laser", {}).get("power_uw", 208))
        field("Camera URL",                  "hardware.camera.url",
              hw.get("camera", {}).get("url", "cam://0"))
        field("Camera exposure (µs)",        "hardware.camera.exposure_time",
              hw.get("camera", {}).get("exposure_time", 500))
        field("Fiber switch COM port",       "hardware.fiber_switch.port",
              hw.get("fiber_switch", {}).get("port", "COM6"))
        field("Motor serial number",         "hardware.polarization_motors.serial_number",
              hw.get("polarization_motors", {}).get("serial_number", "38394984"))

        section("Experiment")
        legs = exp.get("legs", list(range(1, 8)))
        field("Legs",                        "experiment.legs",
              ",".join(map(str, legs)))
        wls = exp.get("wavelengths", [1540, 1545, 1550, 1555, 1560, 1565, 1570])
        field("Wavelengths (nm)",            "experiment.wavelengths",
              ",".join(map(str, wls)))
        wt = exp.get("wait_times", {})
        field("Wait after leg switch (s)",   "experiment.wait_times.after_leg_switch",
              wt.get("after_leg_switch", 1.0))
        field("Wait after wavelength (s)",   "experiment.wait_times.after_wavelength_change",
              wt.get("after_wavelength_change", 0.5))
        fd = exp.get("fringe_detection", {})
        field("Min fringe visibility",       "experiment.fringe_detection.min_visibility",
              fd.get("min_visibility", 0.15))
        field("Max polarization attempts",   "experiment.fringe_detection.max_attempts",
              fd.get("max_attempts", 5))

        section("Output")
        field("Data output directory",       "data.output_dir",
              self.config.get("data", {}).get("output_dir", "./holography_data"))

        ttk.Button(inner, text="Save configuration", style="Accent.TButton",
                   command=self._save_config).pack(anchor="w", pady=(16, 4))

    def _save_config(self):
        import yaml

        try:
            with open(CONFIG_FILE) as f:
                cfg = yaml.safe_load(f) or {}
        except Exception:
            cfg = {}

        for key_path, var in self._cfg_vars.items():
            raw = var.get().strip()
            if "," in raw:
                parts = [p.strip() for p in raw.split(",") if p.strip()]
                try:
                    val = [int(p) if "." not in p else float(p) for p in parts]
                except ValueError:
                    val = parts
            elif raw.lstrip("-").replace(".", "", 1).isdigit():
                val = float(raw) if "." in raw else int(raw)
            else:
                val = raw

            keys = key_path.split(".")
            d = cfg
            for k in keys[:-1]:
                d = d.setdefault(k, {})
            d[keys[-1]] = val

        with open(CONFIG_FILE, "w") as f:
            yaml.dump(cfg, f, default_flow_style=False, sort_keys=False)

        self.config = self._load_config()
        self._log("Configuration saved", "OK")
        messagebox.showinfo("Saved", "Configuration saved to experiment_config.yaml")
