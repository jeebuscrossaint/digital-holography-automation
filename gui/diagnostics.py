# -*- coding: utf-8 -*-
"""Turn raw driver/VISA/serial exceptions into plain-English, actionable hints
shown in the Activity log when a device fails to connect."""

import re


def friendly_error(e: Exception) -> str:
    """Turn raw exception messages into plain-English hints."""
    msg = str(e)
    low = msg.lower()

    # Missing DLL — catches GPIB adapter drivers, Kinesis, Xeneth, etc.
    if "could not find module" in low and ".dll" in low:
        m = re.search(r"['\"]([^'\"]+\.dll)['\"]", msg)
        name = m.group(1).split("\\")[-1] if m else "a required DLL"
        nlow = name.lower()
        if "gpib" in nlow:
            return (f"Missing {name} — install NI-488.2 or Keysight IO Libraries "
                    f"for your GPIB-USB adapter")
        if "polarizer" in nlow or "kinesis" in nlow:
            return "Thorlabs Kinesis DLL not found — install Kinesis software"
        if "xeneth" in nlow or "xenics" in nlow:
            return f"Xeneth SDK not found ({name}) — install Xenics camera software"
        return f"Missing DLL: {name} — check driver installation"

    # Python-level gpib binding actually missing
    if "no module named 'gpib'" in low or "cannot import name 'gpib'" in low:
        return "Python GPIB binding missing — pip install gpib-ctypes"

    # gpib-ctypes installed but the system-level GPIB driver isn't loaded
    if "gpib library not found" in low or "manually load it using _load_lib" in low \
            or ("gpib" in low and "all gpib functions will raise" in low):
        return ("System GPIB driver not loaded — install NI-488.2 (free from ni.com) "
                "or Keysight IO Libraries for your GPIB-USB adapter, then reboot")

    # NI-VISA / pyvisa errors
    if "vi_error_rsrc_nfound" in low or "insufficient location information" in low:
        return ("VISA resource not found at that address — check the discovered "
                "resources logged below")
    if "vi_error_tmo" in low or ("timeout" in low and "visa" in low):
        return "VISA timeout — instrument may be off, busy, or at a different address"
    if "vi_error_nlisteners" in low:
        return "No GPIB listener at that address — wrong address, or instrument is off"
    if "vi_error_io" in low:
        return "VISA I/O error — check cable and instrument power"
    if "no gateway" in low and "visa" in low:
        return ("No VISA backend available — install NI-488.2 / Keysight IO Libraries, "
                "or 'pip install pyvisa-py'")

    # Serial / COM port
    if "could not open port" in low:
        port = re.search(r"'(COM\d+)'", msg)
        p = port.group(1) if port else "the COM port"
        return f"{p} not found or in use — is the device plugged in and the right port set in config?"

    if "polarizer.dll" in low or ("kinesis" in low and "dll" in low):
        return "Thorlabs Kinesis DLL not found — install Kinesis software and plug in motors"
    if "exposuretime" in low:
        return f"Camera property warning (may still work): {msg.splitlines()[0]}"

    # Fallback — strip giant tracebacks, keep first line
    return msg.split("\n")[0][:160]
