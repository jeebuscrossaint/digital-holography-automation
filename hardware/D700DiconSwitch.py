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
    
    def __init__(self, port="COM6", baudrate=9600, timeout=1, auto_detect=True):
        """Open the switch, auto-finding the port if the configured one is stale.

        The switch is driven through an Arduino relay (Caleb's
        BasicSerialCommunication.ino), whose USB-serial port re-enumerates to a
        different COMx after a reboot or a replug — so a hardcoded
        'fiber_switch.port' goes stale and the open fails. We try the configured
        port first, then scan the other USB-serial ports (Arduino-looking ones
        first) and take the first that opens and answers the ID handshake. So
        you never have to hand-edit the COM port again.

        Args:
            port: preferred serial port (tried first); e.g. "COM4"
            baudrate: communication speed (default 9600)
            timeout: read timeout in seconds
            auto_detect: scan other ports if the preferred one fails (default on)
        """
        self.baudrate = baudrate
        self.timeout = timeout
        self.current_position = None
        self.ser, self.port = self._connect(port, auto_detect)
        print(f"Connected to Dicon switch on {self.port}")

    # ── connection helpers ───────────────────────────────────────────────────
    def _open(self, port):
        """Open one port and wait out the Arduino reset/boot (~2 s), then flush
        the "Goodnight moon!" handshake so it doesn't pollute the first reply.
        Opening the port toggles DTR, which RESETS the Arduino; commands sent
        before it finishes booting are dropped (the old "shaky" behaviour)."""
        ser = serial.Serial(port=port, baudrate=self.baudrate, bytesize=8,
                             parity='N', stopbits=1, timeout=self.timeout)
        time.sleep(2.0)
        try:
            ser.reset_input_buffer()
        except Exception:
            pass
        return ser

    @staticmethod
    def _probe(ser):
        """Best-effort ID handshake. Caleb's working driver sends 'ID?' but the
        GP700 manual lists the SCPI '*idn?' — firmware answers one or the other,
        so try both and return the first non-empty reply (or '')."""
        for q in ("*idn?", "ID?"):
            try:
                ser.reset_input_buffer()
                ser.write(q.encode())
                time.sleep(0.3)
                resp = ser.read(64).decode(errors='ignore').strip()
                if resp:
                    return resp
            except Exception:
                pass
        return ""

    def _connect(self, preferred, auto_detect):
        """Return (open_serial, port_name). Tries the preferred port, then the
        other USB-serial ports. Prefers one that answers the ID handshake;
        falls back to the first that merely opens (the rig usually has a single
        USB-serial device, so that's the switch)."""
        candidates = []
        if preferred:
            candidates.append(preferred)
        if auto_detect:
            def usbish(p):
                d = (p.description or "").lower()
                return any(k in d for k in ("arduino", "ch340", "usb serial",
                                            "usb-serial", "ftdi", "serial"))
            for p in sorted(serial.tools.list_ports.comports(),
                            key=usbish, reverse=True):
                if p.device not in candidates:
                    candidates.append(p.device)

        opened_fallback, tried = None, []
        for cand in candidates:
            try:
                ser = self._open(cand)
            except Exception as e:
                tried.append(f"{cand} ({e.__class__.__name__})")
                continue
            if self._probe(ser):
                if opened_fallback is not None:      # release the earlier silent port
                    opened_fallback[0].close()
                return ser, cand                     # answered — this is the switch
            if opened_fallback is None:
                opened_fallback = (ser, cand)        # opened but silent — keep as backup
            else:
                ser.close()
        if opened_fallback is not None:
            return opened_fallback
        raise IOError(
            "Could not open the Dicon switch on any serial port. Tried: "
            + (", ".join(tried) if tried else "<no COM ports found>")
            + ". Check the Arduino is plugged in and not held open by another "
              "program (e.g. the Arduino IDE Serial Monitor).")
    
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
        """Query the device ID (tries '*idn?' then 'ID?', since firmware differs
        on which it answers). An empty reply means the port opened but nothing
        is really answering (wrong device/baud or powered off)."""
        return self._probe(self.ser)

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

