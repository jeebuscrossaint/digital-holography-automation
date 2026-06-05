# -*- coding: utf-8 -*-
"""Switch tab — Dicon GP700 fiber switch (route input fiber to a lantern leg)."""

import threading
import tkinter as tk
from tkinter import ttk

from ..theme import MUTED


class SwitchTabMixin:
    def _build_switch_tab(self):
        tab = ttk.Frame(self.notebook, padding=14)
        self.notebook.add(tab, text="Switch")

        ttk.Label(tab, foreground=MUTED, font=self._font_small,
                  text="Dicon GP700 fiber switch. Routes the input fiber to one of "
                       "N output ports (legs of the photonic lantern)."
                  ).pack(anchor="w", pady=(0, 12))

        big = (self._font_title[0], 26)

        pos = ttk.LabelFrame(tab, text="  Current leg  ", padding=14)
        pos.pack(fill="x", pady=6)
        self._switch_pos_cur = tk.StringVar(value="—")
        ttk.Label(pos, textvariable=self._switch_pos_cur, font=big,
                  width=4, anchor="w").pack(side="left", padx=(0, 20))
        ttk.Label(pos, text="Go to leg", foreground=MUTED).pack(side="left", padx=(0, 6))
        self._switch_pos_target = tk.IntVar(value=1)
        sp = ttk.Spinbox(pos, from_=1, to=16, increment=1,
                         textvariable=self._switch_pos_target, width=6)
        sp.pack(side="left", padx=2)
        sp.bind("<Return>", lambda _e: self._switch_to_leg(int(self._switch_pos_target.get())))
        ttk.Button(pos, text="Move", style="Accent.TButton",
                   command=lambda: self._switch_to_leg(int(self._switch_pos_target.get()))
                   ).pack(side="left", padx=(6, 2))

        quick = ttk.LabelFrame(tab, text="  Quick select  ", padding=14)
        quick.pack(fill="x", pady=6)
        legs = self.config.get("experiment", {}).get("legs", list(range(1, 8)))
        for leg in legs:
            ttk.Button(quick, text=f"Leg {leg}", width=8,
                       command=lambda l=leg: self._switch_to_leg(l)
                       ).pack(side="left", padx=4)

        self._switch_status_var = tk.StringVar(value="Connect to enable controls.")
        ttk.Label(tab, textvariable=self._switch_status_var,
                  foreground=MUTED, font=self._font_small).pack(anchor="w", pady=(14, 0))

    def _switch_to_leg(self, leg: int):
        if not self.switch:
            self._switch_status_var.set("Switch not connected.")
            return
        self._switch_pos_target.set(leg)
        self._switch_pos_cur.set(str(leg))
        self._log(f"Switch → leg {leg}", "INFO")
        self._mark_user_action()
        threading.Thread(target=self._switch_to_leg_worker, args=(leg,),
                         daemon=True).start()

    def _switch_to_leg_worker(self, leg: int):
        try:
            module = self.config.get("hardware", {}).get("fiber_switch", {}).get("module", 1)
            self.switch.move_to_position(module, leg)
        except Exception as e:
            self.msg_queue.put({"type": "log",
                                "text": f"Switch move to leg {leg} failed: {e}",
                                "level": "WARN"})
