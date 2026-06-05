# -*- coding: utf-8 -*-
"""
Created on Wed Feb  4 19:04:20 2026

@author: mecdm

Dicon GP700 Fiber Switch Driver
Based on Dicon GP700 Manual
"""

import time
import serial
import serial.tools.list_ports


class D700DiconSwitch:
    """Driver for Dicon GP700 Fiber Switch
    
    Controls optical fiber switching via RS-232 serial connection.
    Default settings: 9600 baud, 8 data bits, no parity, 1 stop bit

    Command format (verified against Caleb's working driver — the GP700
    uses a lowercase module letter and NO line terminator):
        set:   "i{module} {position}"   e.g. "i1 3" -> module 1 to channel 3
        query: "i{module}?"             e.g. "i1?"
    NOTE: the earlier "M{module} {position}\r\n" form was never valid — the
    switch silently ignored it, so every leg switch was a no-op.
    """
    
    def __init__(self, port="COM6", baudrate=9600, timeout=1):
        """Initialize connection to Dicon fiber switch
        
        Args:
            port: Serial port name (e.g., "COM6")
            baudrate: Communication speed (default 9600)
            timeout: Read timeout in seconds
        """
        self.ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=8,
            parity='N',
            stopbits=1,
            timeout=timeout
        )
        time.sleep(0.5)  # Allow hardware to stabilize
        self.current_position = None
        print(f"Connected to Dicon switch on {port}")
    
    def send_command(self, cmd, read_bytes=16, wait=0.15):
        """Send a raw GP700 command and return the response.

        The GP700 wants the command bytes with NO line terminator (matching
        Caleb's working driver). Returns the decoded response string.
        """
        self.ser.reset_input_buffer()
        self.ser.write(cmd.encode())
        time.sleep(wait)
        return self.ser.read(read_bytes).decode(errors='ignore').strip()

    def move_to_position(self, module, position):
        """Move switch module to specified position.

        Args:
            module: Module number (usually 1)
            position: Output port number (1-N depending on switch config)

        Returns:
            The position set.
        """
        self.ser.reset_input_buffer()
        self.ser.write(f"i{module} {position}".encode())   # GP700: lowercase, no terminator
        self.current_position = position
        print(f"Switched to leg {position}")
        time.sleep(0.3)  # settling time for the optical path
        return position

    def identify(self):
        """Query the device ID ('ID?'). Returns the response, or '' if the
        switch doesn't answer — an empty reply means nothing is really
        talking on this port (wrong device/baud, or switch powered off),
        even though the serial port opened fine."""
        return self.send_command("ID?")

    def get_position(self, module=1):
        """Query current position of switch module.

        The GP700 is driven open-loop (set with 'i{m} {ch}', no readback is
        relied on). If it doesn't answer the query we just return the last
        commanded position — quietly, so we don't spam the log.

        Returns:
            Current position as integer (or last known).
        """
        response = self.send_command(f"i{module}?")
        digits = ''.join(ch for ch in response if ch.isdigit())
        if digits:
            self.current_position = int(digits)
        return self.current_position
    
    def close(self):
        """Close serial connection"""
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("Dicon switch disconnected")
    
    def __del__(self):
        """Cleanup on deletion"""
        try:
            self.close()
        except:
            pass


def list_available_ports():
    """List all available serial ports"""
    ports = serial.tools.list_ports.comports()
    print("Available ports:")
    for p in ports:
        print(f"  {p.device} - {p.description}")
    return ports


if __name__ == '__main__':
    # Test the switch
    list_available_ports()
    switch = D700DiconSwitch(port="COM6")
    
    # Example: Switch between positions
    for leg in range(1, 4):
        print(f"\nTesting leg {leg}")
        switch.move_to_position(1, leg)
        time.sleep(1)
        current = switch.get_position(1)
        print(f"Current position: {current}")
    
    switch.close()

