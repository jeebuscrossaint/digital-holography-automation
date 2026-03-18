"""
capi.py: This file contains the C API for xeneth.dll.
"""

from sys import platform
import ctypes
import ctypes.util


# pylint: disable=protected-access,broad-exception-raised,global-statement,invalid-name

xenethdll = None
if platform != 'win32':
    raise SystemError("This module currently only works on the Windows platform")



def _load_library():
    global xenethdll
    xenethdll = None
    bitness_32 = False
    bitness_64 = False
    error_messages = []

    lib_path = ctypes.util.find_library("xeneth")
    if lib_path is not None:
        try:
            xenethdll = ctypes.WinDLL(lib_path)
            xenethdll._name = 'xeneth'
            _bitness_32 = True
        except OSError as e:
            error_messages.append(f"Failed to load xeneth.dll (32-bit): {e}")

    if xenethdll is None:
        lib_path = ctypes.util.find_library("xeneth64") 
        if lib_path is not None:
            try:
                xenethdll = ctypes.WinDLL(lib_path)
                xenethdll._name = 'xeneth64'
                bitness_64 = True
            except OSError as e:
                error_messages.append(f"Failed to load xeneth64.dll (64-bit): {e}")


    xenethdll._bitness_32 = bitness_32 
    xenethdll._bitness_64 = bitness_64 

    if xenethdll is None:
        error_message = "\n".join(error_messages)
        raise Exception(f"Could not load Xeneth DLL:\n{error_message}\n"
                        "Is Xeneth installed and does its bitness match the Python interpreter?")

    # inject '_path' attribute to xenethdll
    xenethdll._path = ctypes.util.find_library(xenethdll._name)

_load_library()