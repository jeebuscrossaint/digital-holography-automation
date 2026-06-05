"""Probe the DiCon GP700 fiber switch — confirm it actually responds.

Background: the old D700DiconSwitch sent "M1 3\r\n", which the GP700 ignores
(every leg switch was a silent no-op). Caleb's working driver uses lowercase
"i1 3" with NO terminator. This probe sends both forms and prints the RAW
responses so you can see which one the switch actually answers.

Run (Xeneth/app can stay open; this only touches the serial port):
    uv run python tools/probe_switch.py
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "hardware"))

import serial  # noqa: E402
import yaml     # noqa: E402

cfg = yaml.safe_load(open(ROOT / "experiment_config.yaml"))
sw = cfg["hardware"]["fiber_switch"]
PORT = sw.get("port", "COM3")
BAUD = sw.get("baudrate", 9600)
MOD  = sw.get("module", 1)

print(f"Opening {PORT} @ {BAUD} ...")
ser = serial.Serial(PORT, BAUD, bytesize=8, parity="N", stopbits=1, timeout=1)
time.sleep(0.5)


def ask(cmd, wait=0.2, n=32):
    ser.reset_input_buffer()
    ser.write(cmd.encode())
    time.sleep(wait)
    resp = ser.read(n)
    print(f"  sent {cmd!r:16} -> {resp!r}")
    return resp


print("\n--- device identity ---")
ask("ID?")

print("\n--- OLD (broken) form: M1 3 + CRLF — expect no/garbage response ---")
ask("M1 3\r\n")
ask("M1?\r\n")

print(f"\n--- NEW (Caleb) form: i{MOD} <leg>, query i{MOD}? ---")
for leg in range(1, 8):
    ser.reset_input_buffer()
    ser.write(f"i{MOD} {leg}".encode())   # set, no terminator
    time.sleep(0.4)
    q = ask(f"i{MOD}?")                    # query back
    digits = "".join(c for c in q.decode(errors="ignore") if c.isdigit())
    ok = digits == str(leg)
    print(f"  leg {leg}: switch reports {digits or '??'}  "
          f"{'OK' if ok else '<-- mismatch'}")

ser.close()
print("\nDone. If the i-form queries echo the leg you set, switching works.")
