# -*- coding: utf-8 -*-
import os
import pyvisa as visa

# HP 8168E wavelength range (nm)
_WL_MIN = 1475.0
_WL_MAX = 1575.0

# Keysight IO Libraries: on some installs the IVI dispatcher in System32
# fails to forward to the vendor implementation (VI_ERROR_LIBRARY_NFOUND),
# even with the suite installed. Loading ktvisa32.dll directly works as
# long as its sibling support DLLs are on the search path.
_KT_DLL_DIRS = (
    r"C:\Program Files\IVI Foundation\VISA\Win64\ktvisa\ktbin",
    r"C:\Program Files\IVI Foundation\VISA\Win64\Bin",
    r"C:\Program Files\Keysight\IO Libraries Suite\bin",
    r"C:\Program Files\Keysight\IO Libraries Suite\lib_x64",
)
_KT_VISA_64 = r"C:\Program Files\IVI Foundation\VISA\Win64\ktvisa\ktbin\ktvisa32.dll"

for _d in _KT_DLL_DIRS:
    if os.path.exists(_d):
        try:
            os.add_dll_directory(_d)
        except (AttributeError, OSError):
            pass
        os.environ["PATH"] = _d + os.pathsep + os.environ.get("PATH", "")


def _make_resource_manager():
    """Prefer Keysight 64-bit VISA by direct path; fall back to default backend."""
    if os.path.exists(_KT_VISA_64):
        try:
            return visa.ResourceManager(_KT_VISA_64)
        except Exception:
            pass
    return visa.ResourceManager()


class HPTunableLaserSource:
    def __init__(self, TLName='GPIB0::24::INSTR'):
        rm = _make_resource_manager()
        try:
            self.TL = rm.open_resource(TLName)
        except Exception:
            try:
                rm.open_resource(TLName).close()
            except Exception:
                pass
            self.TL = rm.open_resource(TLName)

        self.TL.timeout = 15000
        self.TL.read_termination = '\n'
        self.TL.write_termination = '\n'

        # The HP 8168 silently rejects unrecognized/invalid commands — the
        # only sign is an entry in its error queue. Clear stale errors from
        # any prior session so checkError() reflects only what we send.
        self.last_error = None
        try:
            self.TL.write("*CLS")
        except Exception:
            pass

    # --- error checking (the 8168 fails writes silently) ---

    def checkError(self):
        """Drain and return the instrument error queue (:SYST:ERR?).

        Returns a list of error strings. A clean queue is ['+0,"No error"'].
        Use this after a suspicious operation — the 8168 won't raise, it just
        queues the error and moves on."""
        errors = []
        old = self.TL.timeout
        self.TL.timeout = 2000
        try:
            for _ in range(20):
                resp = self.TL.query(":SYST:ERR?").strip()
                errors.append(resp)
                if resp.split(",")[0].strip() in ("0", "+0"):
                    break
        except Exception:
            pass
        finally:
            self.TL.timeout = old
        return errors

    def _safe_write(self, cmd, check=True):
        """Write a command and (optionally) confirm the 8168 accepted it via
        the error queue. Records the first rejection to self.last_error and
        returns True if accepted. Does NOT raise, so a bad command mid-sweep
        won't abort the run — callers check the return / self.last_error."""
        self.TL.write(cmd)
        if not check:
            return True
        old = self.TL.timeout
        self.TL.timeout = 2000
        try:
            err = self.TL.query(":SYST:ERR?").strip()
        except Exception:
            self.TL.timeout = old
            return True  # can't verify; assume OK rather than block
        self.TL.timeout = old
        if err.split(",")[0].strip() not in ("0", "+0"):
            self.last_error = f"{cmd!r} rejected by laser: {err}"
            print(f"[laser] {self.last_error}")
            return False
        return True

    # --- output ---

    def outputState(self, tf):
        # 8168E listens to the short :OUTP:STAT form, not :SOUR:POW:STAT
        self._safe_write(":OUTP:STAT 1" if tf else ":OUTP:STAT 0")

    def isOutputOn(self):
        return self.TL.query(":OUTP:STAT?").strip()

    # --- power ---

    def powerAmplitude(self, num, unit="UW"):
        """Set output power. num is in the given unit; accepts MIN/MAX/DEF.
        Use unit 'UW' (microwatts), 'DBM', 'NW', 'MW', 'W', etc. The
        short :POW form is what the HP 8168E actually responds to."""
        if unit:
            self._safe_write(f":POW {num}{unit}")
        else:
            self._safe_write(f":POW {num}")

    def checkPowerAmplitude(self, string=''):
        return self.TL.query(f":POW? {string}").strip()

    def changePowerUnit(self, string):
        """8168 :POW:UNIT takes a numeric code (0=dBm, 1=Watt), NOT a unit
        string like 'UW' — that returns -141 'Invalid character data'. Map
        common names to the code. Actual power values are still set with an
        inline suffix (e.g. ':POW 208UW'), which the instrument does accept."""
        s = str(string).strip().upper()
        code = 0 if s in ("DBM", "DB") else 1   # everything watt-based -> 1
        self._safe_write(f":POW:UNIT {code}")

    def checkPowerUnit(self):
        return self.TL.query(":POW:UNIT?").strip()

    # --- wavelength ---

    def changeWavelength(self, nm):
        """Set wavelength in nm (1475–1575). Accepts float, int, or 'MIN'/'MAX'/'DEF'."""
        if isinstance(nm, (int, float)):
            if not (_WL_MIN <= nm <= _WL_MAX):
                raise ValueError(f"Wavelength {nm} nm out of range [{_WL_MIN}, {_WL_MAX}]")
            self._safe_write(f":WAVE {nm:.4f}NM")
        else:
            self._safe_write(f":WAVE {nm}")

    def checkWavelength(self, string=''):
        """Return current wavelength in nm. The 8168E reports in meters
        (e.g. 1.55e-6) via the short :WAVE? form; convert if needed."""
        raw = self.TL.query(f":WAVE? {string}").strip()
        try:
            v = float(raw)
            return v * 1e9 if abs(v) < 1e-3 else v
        except ValueError:
            return raw

    def checkWavelengthReference(self):
        return self.TL.query(":WAVE:REF?").strip()

    def setReferenceWavelength(self):
        self.TL.write("WAVE:REF:DISP")

    # --- coherence control ---

    def coherenceControl(self, tf):
        """Enable/disable coherence control (reduces linewidth)."""
        self.TL.write(f":SOUR:COHE:CONT {'ON' if tf else 'OFF'}")

    def checkCoherenceControl(self):
        return self.TL.query(":SOUR:COHE:CONT?").strip()

    # --- modulation ---

    def setAmplitudeFrequency(self, freq):
        self.TL.write(f":SOUR:AM:INT:FREQ {freq}")

    def whatAmplitudeFrequency(self):
        return self.TL.query(":SOUR:AM:INT:FREQ?").strip()

    def typeOfModulation(self, num):
        """0=internal, 1=coherent control, 2=external."""
        self.TL.write(f":SOUR:AM:SOUR {num}")

    def whatTypeOfModulation(self):
        return self.TL.query(":SOUR:AM:SOUR?").strip()

    def modulationState(self, tf):
        self.TL.write(f":SOUR:AM:STAT {'1' if tf else '0'}")

    def modulationType(self, tf):
        """False=constant, True=low while changing."""
        self.TL.write(f":SOURCE:MODOUT {'0' if tf else '1'}")

    # --- frequency offset ---

    def setFrequencyOffset(self, num):
        self.TL.write(f"WAVE:FREQ {num}")

    def checkFrequencyOffset(self):
        return self.TL.query(":WAVE:FREQ?").strip()

    # --- display ---

    def displayEnable(self, tf):
        self.TL.write(f":DISP:ENAB {'1' if tf else '0'}")

    def isDisplayOn(self):
        return self.TL.query(":DISP:ENAB?").strip()

    # --- misc ---

    def clearStatus(self):
        self.TL.write("*CLS")

    def checkLaserCondition(self):
        """Bit 8: output power exceeded; Bit 9: powering up."""
        return self.TL.query(":STAT:OPER:COND?").strip()

    def identify(self):
        return self.TL.query("*IDN?").strip()

    def closeConnection(self):
        self.TL.close()

    def __del__(self):
        try:
            self.TL.close()
        except Exception:
            pass
