# -*- coding: utf-8 -*-
"""Instrument drivers.

    XenicsCam              Xenics Bobcat 320 GigE (InGaAs, 320x256)
    HPTunableLaserSource   HP/Agilent 8168E tunable laser (GPIB)
    D700DiconSwitch        DiCon GP700 fiber switch (RS-232)
    polMotors              Thorlabs MPC320 polarization paddles (USB/Kinesis)
    ThorLabsPowerMeter     Thorlabs power meter
    FiberSwitchWithArduino Arduino-driven switch (alternative to the GP700)

Import these as submodules -- ``from holo.hardware.XenicsCam import xCam``.
They are deliberately NOT imported here: each one pulls in a vendor DLL or a
serial/VISA stack, most of which are absent on a dev machine, so importing the
package must not require any of them to be installed.

On Windows the Xeneth DLL directory has to be registered before XenicsCam is
imported. ``holo.runtime.bootstrap()`` does that; the GUI and CLI both call it
at startup.
"""
