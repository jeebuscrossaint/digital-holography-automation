"""Bundle the PySide6 (Qt6) GUI (main.py) into a single native Windows .exe.

The result is a standalone desktop app — no Python, Node, web server, or
WebView2 needed on the target machine. (The two hardware SDKs — Keysight IO
Libraries and Xenics Xeneth — still install separately; their DLLs load at
runtime. See LAB_SETUP.md.)

    uv run python tools/build_app.py            # -> dist/Digital Holography.exe (windowed)
    uv run python tools/build_app.py --console  # console build for debugging import errors
"""
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEP = ";" if sys.platform == "win32" else ":"


def add_data(src: str, dest: str):
    return ["--add-data", f"{ROOT / src}{SEP}{dest}"]


def main():
    console = "--console" in sys.argv

    # Third-party deps used by the lazily-imported hardware/processing modules.
    # PyInstaller can't see them through main.py's runtime sys.path imports, so
    # name them explicitly.
    hidden = [
        "yaml", "numpy", "scipy", "scipy.special", "scipy.optimize",
        "scipy.signal", "scipy.ndimage", "matplotlib", "PIL", "PIL.Image",
        "pyvisa", "pyvisa_py", "gpib_ctypes", "serial", "serial.tools.list_ports",
        # repo-root modules main.py imports lazily
        "fringe_detection", "data_processing", "multiport_reconstruction",
        "pipeline",
        # hardware drivers (also bundled as data + reachable via runtime sys.path)
        "XenicsCam", "HPTunableLaserSource", "D700DiconSwitch", "polMotors",
        "MMF", "calebsUsefulFunctions",
    ]
    collect = ["PySide6", "xenics"]   # packages that ship data files / submodules / Qt plugins

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile", "--noconfirm", "--clean",
        "--name", "Digital Holography",
        "--icon", str(ROOT / "gui" / "app_icon.ico"),
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build" / "app"),
        "--specpath", str(ROOT / "build" / "app"),
        # let PyInstaller resolve + analyze the hardware/lib/root modules so
        # their imports get bundled, AND ship the source as data so the app's
        # runtime sys.path inserts still find them.
        "--paths", str(ROOT),
        "--paths", str(ROOT / "hardware"),
        "--paths", str(ROOT / "lib"),
        *add_data("hardware", "hardware"),
        *add_data("lib", "lib"),
        *add_data("experiment_config.yaml", "."),
        # app icon — bundled into gui/ so the window/taskbar icon resolves
        *add_data("gui/app_icon.ico", "gui"),
        *add_data("gui/app_icon.png", "gui"),
    ]
    if (ROOT / "vendor").exists():
        cmd += add_data("vendor", "vendor")
    cmd += ["--console"] if console else ["--windowed"]
    for h in hidden:
        cmd += ["--hidden-import", h]
    for c in collect:
        cmd += ["--collect-all", c]
    cmd.append(str(ROOT / "main.py"))

    print(" ".join(cmd), "\n")
    subprocess.check_call(cmd)
    suffix = ".exe" if sys.platform == "win32" else ""
    print(f"\nBuilt -> dist/Digital Holography{suffix}")


if __name__ == "__main__":
    main()
