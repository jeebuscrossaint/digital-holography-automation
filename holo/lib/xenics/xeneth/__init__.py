"""
xeneth.capi package

Wrapper for XenEth C SDK
"""
from holo.lib.xenics.xeneth.capi.enums import XEnumerationFlags, XDeviceStates, XGetFrameFlags
from holo.lib.xenics.xeneth.xcamera import XCamera
from holo.lib.xenics.xeneth.discovery import enumerate_devices



# Export essentials for the high level API
__all__ = ['XEnumerationFlags', 'XDeviceStates',
     'enumerate_devices', 'XCamera', 'XGetFrameFlags']
