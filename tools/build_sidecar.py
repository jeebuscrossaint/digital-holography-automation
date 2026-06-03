"""Bundle the Python sidecar into a single .exe using PyInstaller.

Lab members can then run the Tauri app without installing Python / uv
at all — the .exe is shipped as a Tauri resource and spawned by Rust.

Usage:
    uv run python tools/build_sidecar.py
Outputs:
    app/src-tauri/binaries/holography-sidecar-<target-triple>.exe

The target-triple suffix is required by Tauri's sidecar mechanism.
"""

import platform
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SIDECAR_PY = ROOT / "sidecar" / "main.py"
HARDWARE   = ROOT / "hardware"
LIB        = ROOT / "lib"
VENDOR     = ROOT / "vendor"
OUT_DIR    = ROOT / "app" / "src-tauri" / "binaries"
BUILD_DIR  = ROOT / "build" / "sidecar"


def rust_target_triple() -> str:
    """Tauri expects e.g. holography-sidecar-x86_64-pc-windows-msvc.exe"""
    out = subprocess.check_output(["rustc", "-vV"], text=True)
    for line in out.splitlines():
        if line.startswith("host:"):
            return line.split()[1]
    raise RuntimeError("Could not determine rust host triple")


def main():
    if not SIDECAR_PY.exists():
        sys.exit(f"sidecar source missing: {SIDECAR_PY}")

    triple = rust_target_triple()
    print(f"Building sidecar for {triple}…")

    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    extras = []
    if HARDWARE.exists():
        extras += ["--add-data", f"{HARDWARE}{';' if sys.platform == 'win32' else ':'}hardware"]
    if LIB.exists():
        extras += ["--add-data", f"{LIB}{';' if sys.platform == 'win32' else ':'}lib"]
    if VENDOR.exists():
        extras += ["--add-data", f"{VENDOR}{';' if sys.platform == 'win32' else ':'}vendor"]

    # Hidden imports the sidecar uses dynamically
    hidden = [
        "yaml", "numpy", "scipy", "pyvisa", "pyvisa_py",
        "gpib_ctypes", "PIL", "PIL.Image", "serial",
        "xenics.xeneth",
    ]
    hidden_args = []
    for h in hidden:
        hidden_args += ["--hidden-import", h]

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--noconfirm",
        "--clean",
        "--name", "holography-sidecar",
        "--distpath", str(OUT_DIR),
        "--workpath", str(BUILD_DIR / "work"),
        "--specpath", str(BUILD_DIR),
        *extras,
        *hidden_args,
        str(SIDECAR_PY),
    ]
    print(" ".join(cmd))
    subprocess.check_call(cmd)

    # PyInstaller produces holography-sidecar.exe; Tauri wants the
    # target-triple suffix on the filename.
    built = OUT_DIR / ("holography-sidecar.exe" if sys.platform == "win32" else "holography-sidecar")
    if not built.exists():
        sys.exit("PyInstaller did not produce the expected file")
    suffix = ".exe" if sys.platform == "win32" else ""
    final = OUT_DIR / f"holography-sidecar-{triple}{suffix}"
    if final.exists(): final.unlink()
    shutil.move(str(built), str(final))
    print(f"\nsidecar built -> {final}")


if __name__ == "__main__":
    main()
