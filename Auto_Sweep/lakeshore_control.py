# -*- coding: utf-8 -*-
"""
Lake Shore Model 335 Temperature Controller Driver
===================================================
Reusable driver for the Lake Shore 335 cryogenic temperature controller.

Communicates via RS-232 serial (ASRL) or GPIB. Handles:
  - Temperature readout (channels A, B, C, D)
  - Setpoint control (Loop 1 / Loop 2)
  - Heater range and heater output percentage
  - PID parameter read/write
  - Safety: all-heaters-off

Serial settings (auto-configured for ASRL):
  Baud 57600, 7 data bits, odd parity, 1 stop bit

Usage:
    from lakeshore_control import LakeShore335

    ls = LakeShore335("ASRL4::INSTR")
    print(ls.get_temperature("A"))
    ls.set_temperature(50.0, loop=1)
    ls.set_pid(100, 5, 0, loop=1)
"""

from typing import Optional, Tuple

import pyvisa
from pyvisa.constants import Parity, StopBits


class LakeShore335:
    """PyVISA driver for the Lake Shore Model 335 temperature controller."""

    RANGE_NAMES = {0: "Off", 1: "Low", 2: "Medium", 3: "High"}

    def __init__(
        self,
        visa_address: str,
        resource_manager: Optional[pyvisa.ResourceManager] = None,
    ):
        if not visa_address:
            raise ValueError("visa_address must not be empty")

        self.visa_address = visa_address
        self.resource_manager = resource_manager or pyvisa.ResourceManager()
        self.device = self.resource_manager.open_resource(visa_address)

        # Serial port configuration for Model 335 USB
        if "ASRL" in visa_address.upper():
            self.device.baud_rate = 57600
            self.device.data_bits = 7
            self.device.parity = Parity.odd
            self.device.stop_bits = StopBits.one
            self.device.timeout = 3000
            self.device.read_termination = "\n"
            self.device.write_termination = "\n"
        else:
            self.device.timeout = 3000
            self.device.read_termination = "\n"
            self.device.write_termination = "\n"

        self.identity = self.query("*IDN?")

    # ---- low-level I/O ----

    def write(self, command: str) -> None:
        self.device.write(command)

    def query(self, command: str) -> str:
        return self.device.query(command).strip()

    # ---- temperature ----

    def get_temperature(self, channel: str = "A") -> float:
        """Read temperature from input channel (A, B, C, D)."""
        return float(self.query(f"KRDG? {channel}"))

    # ---- setpoint ----

    def set_temperature(self, setpoint: float, loop: int = 1) -> None:
        """Set target temperature for control loop (1 or 2)."""
        self.write(f"SETP {loop},{setpoint}")

    def get_setpoint(self, loop: int = 1) -> float:
        """Read current setpoint for control loop."""
        return float(self.query(f"SETP? {loop}"))

    # ---- heater ----

    def set_heater_range(self, output: int, range_level: int) -> None:
        """Set heater range: 0=Off, 1=Low, 2=Medium, 3=High."""
        self.write(f"RANGE {output},{range_level}")

    def get_heater_range(self, output: int = 1) -> int:
        """Read heater range setting."""
        return int(float(self.query(f"RANGE? {output}")))

    def get_heater_percent(self, output: int = 1) -> float:
        """Read heater output percentage."""
        return float(self.query(f"HTR? {output}"))

    # ---- PID ----

    def set_pid(self, p: float, i: float, d: float, loop: int = 1) -> None:
        """Set PID parameters for control loop."""
        self.write(f"PID {loop},{p},{i},{d}")

    def get_pid(self, loop: int = 1) -> Tuple[float, float, float]:
        """Read PID parameters. Returns (P, I, D) tuple."""
        values = self.query(f"PID? {loop}").split(",")
        if len(values) != 3:
            raise RuntimeError(f"Unexpected PID response: {values!r}")
        return tuple(map(float, values))  # type: ignore[return-value]

    # ---- safety ----

    def all_heaters_off(self) -> None:
        """Emergency: set both heater output ranges to OFF."""
        self.set_heater_range(1, 0)
        self.set_heater_range(2, 0)

    # ---- cleanup ----

    def close(self) -> None:
        """Close the VISA session."""
        try:
            self.device.close()
        except Exception:
            pass


# =========================================================================
# Duck-typing helper functions
# =========================================================================
# These functions work with *any* object that looks like a LakeShore 335
# driver — whether it's the LakeShore335 class above, the external
# Lakeshore335 pip package, or the fallback class from power_sweep_auto.py.
#
# They try multiple method names and fall back to raw VISA writes, so
# they survive API variations across different driver versions.
# =========================================================================

def configure_lakeshore_serial(temp_reader, resource_string: str = None):
    """Set RS-232 parameters if the resource is a serial (ASRL) connection.

    Args:
        temp_reader: a LakeShore driver object
        resource_string: VISA address (defaults to config.resource_lakeshore)
    """
    if resource_string is None:
        from config import resource_lakeshore as resource_string

    if "ASRL" not in resource_string.upper():
        return

    for attr in ["inst", "visa", "device", "ser", "com"]:
        if hasattr(temp_reader, attr):
            target = getattr(temp_reader, attr)
            if hasattr(target, "baud_rate"):
                target.baud_rate = 57600
                target.data_bits = 7
                target.parity = pyvisa.constants.Parity.odd
                target.read_termination = "\n"
                target.write_termination = "\n"


def _raw_lakeshore_handle(temp_reader):
    """Find the raw VISA handle on a LakeShore driver object.

    Introspects common attribute names and returns the first one
    that has a ``.write()`` method.
    """
    for attr in ["inst", "visa", "device", "ser", "com"]:
        if hasattr(temp_reader, attr):
            target = getattr(temp_reader, attr)
            if hasattr(target, "write"):
                return target
    return None


def set_lakeshore_temperature(temp_reader, target_k: float):
    """Set temperature setpoint on *any* LakeShore driver.

    Tries method names in order: set_temperature, set_setpoint,
    setpoint, set_temperature_setpoint.  Falls back to raw VISA
    ``SETP 1,{target_k}``.
    """
    method_names = [
        "set_temperature",
        "set_setpoint",
        "setpoint",
        "set_temperature_setpoint",
    ]

    print(f"[DEBUG] Setting LakeShore target: {target_k:.3f} K")

    for method_name in method_names:
        method = getattr(temp_reader, method_name, None)
        if callable(method):
            try:
                method(target_k)
            except TypeError:
                method(1, target_k)
            return

    raw = _raw_lakeshore_handle(temp_reader)
    if raw is not None:
        print(f"[DEBUG] Using raw VISA to set target: {target_k:.3f} K")
        raw.write(f"SETP 1,{target_k}")
        return

    raise AttributeError(
        "Could not find a LakeShore setpoint method or raw VISA handle."
    )


def set_lakeshore_pid(temp_reader, p: float, i: float, d: float):
    """Set PID parameters on *any* LakeShore driver.

    Tries ``temp_reader.set_pid(p, i, d)`` first, then falls back
    to raw VISA ``PID 1,{p},{i},{d}``.
    """
    print(f"[DEBUG] Setting LakeShore PID: P={p}, I={i}, D={d}")

    if hasattr(temp_reader, "set_pid"):
        try:
            temp_reader.set_pid(p, i, d)
            return
        except Exception as e:
            print(f"[DEBUG] set_pid failed: {e}")

    raw = _raw_lakeshore_handle(temp_reader)
    if raw is not None:
        print(f"[DEBUG] Using raw VISA to set PID: P={p}, I={i}, D={d}")
        raw.write(f"PID 1,{p},{i},{d}")
        return

    print(f"[Warning] Could not set PID: P={p}, I={i}, D={d}")


def get_lakeshore_temperature(temp_reader) -> float:
    """Read temperature from *any* LakeShore driver.

    Tries ``.get_temperature()`` first, then raw ``KRDG? A`` query.
    Returns None if both fail.
    """
    try:
        return float(temp_reader.get_temperature())
    except Exception:
        pass

    try:
        return float(temp_reader.query("KRDG? A"))
    except Exception:
        pass

    return None
