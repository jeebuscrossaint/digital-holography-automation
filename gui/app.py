# -*- coding: utf-8 -*-
"""HolographyApp — the Qt application window, composed from one mixin per
concern (same decomposition as before, now on PySide6/Qt6).

Worker threads never touch widgets directly: they call ``self._post(msg)``,
which emits a Qt signal. Qt delivers that signal to the GUI thread (queued
across threads automatically), where ``_dispatch_msg`` updates the UI — this
replaces the old queue + ``after()`` polling pump, and is what makes the
background hardware I/O safe without freezing the window."""

import threading

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QMainWindow

from . import runtime
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

        self._cam_first_frame_logged = False
        threading.Thread(target=self._background_poller,   daemon=True).start()
        threading.Thread(target=self._camera_preview_loop, daemon=True).start()

    def _post(self, msg: dict):
        """Thread-safe: hand a message dict to the GUI thread."""
        self._bridge.message.emit(msg)

    def closeEvent(self, event):
        """Window close: stop experiment, disconnect hardware, then exit."""
        self._stop_background.set()
        if self.experiment_running:
            self.stop_event.set()
        self._shutdown_hardware()
        event.accept()


def main():
    runtime.setup_logfile()
    app = QApplication([])
    apply_theme(app)
    win = HolographyApp()
    win.show()
    app.exec()
