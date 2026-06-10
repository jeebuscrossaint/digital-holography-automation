# -*- coding: utf-8 -*-
"""HolographyApp — the Qt application window, composed from one mixin per
concern (same decomposition as before, now on PySide6/Qt6).

Worker threads never touch widgets directly: they call ``self._post(msg)``,
which emits a Qt signal. Qt delivers that signal to the GUI thread (queued
across threads automatically), where ``_dispatch_msg`` updates the UI — this
replaces the old queue + ``after()`` polling pump, and is what makes the
background hardware I/O safe without freezing the window."""

import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMainWindow

from . import runtime

_ICON = str(Path(__file__).resolve().parent / "app_icon.ico")
from .style import apply_theme
from .shell import ShellMixin
from .connection import ConnectionMixin
from .camera import CameraMixin
from .experiment import ExperimentMixin
from .tabs.run import RunTabMixin
from .tabs.laser import LaserTabMixin
from .tabs.switch import SwitchTabMixin
from .tabs.polarization import PolarizationTabMixin
from .tabs.config import ConfigTabMixin
from .tabs.results import ResultsTabMixin


class _Bridge(QObject):
    """Carries worker-thread messages onto the GUI thread via one signal."""
    message = Signal(object)


class HolographyApp(
    QMainWindow,
    ShellMixin,
    ConnectionMixin,
    CameraMixin,
    ExperimentMixin,
    RunTabMixin,
    LaserTabMixin,
    SwitchTabMixin,
    PolarizationTabMixin,
    ConfigTabMixin,
    ResultsTabMixin,
):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Photonic Lantern Holography")
        self.resize(1320, 880)
        self.setMinimumSize(1100, 720)

        self.hardware_connected = False
        self.experiment_running = False
        self.stop_event = threading.Event()
        self._stop_background = threading.Event()

        self.laser  = None
        self.camera = None
        self.switch = None
        self.motors = None
        self.config = self._load_config()

        # Thread → GUI bridge. Emitting from any thread is safe; the slot runs
        # on the GUI thread.
        self._bridge = _Bridge()
        self._bridge.message.connect(self._dispatch_msg)

        self._build_ui()

        self.setWindowIcon(QIcon(_ICON))

        self._cam_first_frame_logged = False
        # Keep references so close() can wait for them to actually exit.
        self._bg_thread  = threading.Thread(target=self._background_poller,   daemon=True)
        self._cam_thread = threading.Thread(target=self._camera_preview_loop, daemon=True)
        self._bg_thread.start()
        self._cam_thread.start()

    def _post(self, msg: dict):
        """Thread-safe: hand a message dict to the GUI thread."""
        self._bridge.message.emit(msg)

    def closeEvent(self, event):
        """Window close (incl. Alt+F4): stop the background threads and WAIT for
        them to exit BEFORE closing hardware. Otherwise a camera frame-grab in
        flight collides with the camera close and jams the Xeneth SDK — it keeps
        the handle, so the next launch can't connect (the reboot trap)."""
        self._stop_background.set()
        if self.experiment_running:
            self.stop_event.set()
        for t in (getattr(self, "_bg_thread", None), getattr(self, "_cam_thread", None)):
            if t is not None and t.is_alive():
                t.join(timeout=2.5)        # let any in-flight grab finish first
        self._shutdown_hardware()
        event.accept()


def main():
    runtime.setup_logfile()
    app = QApplication([])
    apply_theme(app)
    app.setWindowIcon(QIcon(_ICON))
    win = HolographyApp()
    win.show()
    app.exec()
