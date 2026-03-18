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
    
    Command format: "M{module} {position}\r\n"
    Example: "M1 2" moves module 1 to position 2
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
    
    def send_command(self, cmd):
        """Send raw command and return response
        
        Args:
            cmd: Command string (will append \r\n automatically)
            
        Returns:
            Response string from device
        """
        full_cmd = cmd.strip() + "\r\n"
        self.ser.write(full_cmd.encode())
        time.sleep(0.2)  # Wait for switch to respond/execute
        response = self.ser.readline().decode(errors='ignore').strip()
        return response
    
    def move_to_position(self, module, position):
        """Move switch module to specified position
        
        Args:
            module: Module number (usually 1)
            position: Output port number (1-N depending on switch config)
            
        Returns:
            Response from switch
        """
        cmd = f"M{module} {position}"
        response = self.send_command(cmd)
        self.current_position = position
        print(f"Switched to leg {position}")
        time.sleep(0.3)  # Additional settling time for optical path
        return response
    
    def get_position(self, module=1):
        """Query current position of switch module
        
        Args:
            module: Module number to query
            
        Returns:
            Current position as integer
        """
        cmd = f"M{module}?"
        response = self.send_command(cmd)
        try:
            position = int(response.split()[-1])
            self.current_position = position
            return position
        except:
            print(f"Could not parse position from response: {response}")
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

