# -*- coding: utf-8 -*-
"""HolographyApp — the application window, composed from one mixin per concern.

The mixins live in sibling modules and all operate on this class's ``self``;
splitting them out keeps each file focused while the runtime object stays a
single cohesive app (no behavior change from the original monolith).
"""

import threading
import queue
import tkinter as tk

from . import runtime
from .theme import ThemeMixin
from .shell import ShellMixin
from .camera import CameraMixin
from .connection import ConnectionMixin
from .experiment import ExperimentMixin
from .tabs.run import RunTabMixin
from .tabs.laser import LaserTabMixin
from .tabs.switch import SwitchTabMixin
from .tabs.polarization import PolarizationTabMixin
from .tabs.config import ConfigTabMixin
from .tabs.results import ResultsTabMixin


class HolographyApp(
    ShellMixin,
    ThemeMixin,
    RunTabMixin,
    CameraMixin,
    LaserTabMixin,
    SwitchTabMixin,
    PolarizationTabMixin,
    ConfigTabMixin,
    ResultsTabMixin,
    ConnectionMixin,
    ExperimentMixin,
):
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Photonic Lantern Holography")
        self.root.geometry("1320x880")
        self.root.minsize(1100, 720)

        self.hardware_connected = False
        self.experiment_running = False
        self.stop_event = threading.Event()
        self.msg_queue: queue.Queue = queue.Queue()

        self.laser  = None
        self.camera = None
        self.switch = None
        self.motors = None
        self.config = self._load_config()

        self._setup_theme()
        self._build_ui()
        self._poll_queue()
        self._stop_background = threading.Event()
        threading.Thread(target=self._background_poller,  daemon=True).start()
        threading.Thread(target=self._camera_preview_loop, daemon=True).start()
        self._cam_first_frame_logged = False
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        """Window close: stop experiment, disconnect hardware, then exit."""
        self._stop_background.set()
        if self.experiment_running:
            self.stop_event.set()
        self._shutdown_hardware()
        self.root.destroy()


def main():
    runtime.setup_logfile()
    root = tk.Tk()
    HolographyApp(root)
    root.mainloop()
