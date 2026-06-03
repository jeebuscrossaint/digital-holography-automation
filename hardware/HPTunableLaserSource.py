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

    # --- output ---

    def outputState(self, tf):
        self.TL.write(f":SOUR:POW:STAT {'ON' if tf else 'OFF'}")

    def isOutputOn(self):
        return self.TL.query(":SOUR:POW:STAT?").strip()

    # --- power ---

    def powerAmplitude(self, num, unit="UW"):
        """Set output power. num is in the given unit; accepts MIN/MAX/DEF.
        Use unit 'UW' (microwatts), 'DBM', 'NW', 'MW', 'W', etc. The
        short :POW form is what the HP 8168E actually responds to."""
        if unit:
            self.TL.write(f":POW {num}{unit}")
        else:
            self.TL.write(f":POW {num}")

    def checkPowerAmplitude(self, string=''):
        return self.TL.query(f":POW? {string}").strip()

    def changePowerUnit(self, string):
        self.TL.write(f":POW:UNIT {string}")

    def checkPowerUnit(self):
        return self.TL.query(":POW:UNIT?").strip()

    # --- wavelength ---

    def changeWavelength(self, nm):
        """Set wavelength in nm (1475–1575). Accepts float, int, or 'MIN'/'MAX'/'DEF'."""
        if isinstance(nm, (int, float)):
            if not (_WL_MIN <= nm <= _WL_MAX):
                raise ValueError(f"Wavelength {nm} nm out of range [{_WL_MIN}, {_WL_MAX}]")
            self.TL.write(f":WAVE {nm:.4f}NM")
        else:
            self.TL.write(f":WAVE {nm}")

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
