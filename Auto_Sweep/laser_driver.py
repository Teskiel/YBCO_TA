# -*- coding: utf-8 -*-
"""
Keysight N7779C Laser Driver
============================
Reusable driver module for the Keysight N7779C tunable laser.

Provides:
  - Connection lifecycle (connect / disconnect / health check)
  - Power control with separate output on/off
  - Wavelength control (1520-1570 nm typical for C-band)
  - Emergency physical shutdown and restart
  - Automatic disconnection recovery with staged retries
  - Full status readback

Usage:
    from laser_driver import LaserController

    laser = LaserController("TCPIP0::169.254.77.29::INSTR")
    if laser.connect():
        laser.set_wavelength(1550)
        laser.set_power(5)
        print(laser.get_status())
"""

import pyvisa
from time import sleep
from typing import Optional


class LaserController:
    """Keysight N7779C tunable laser controller.

    Communicates via TCPIP/VISA. Manages power, wavelength, output state,
    and provides emergency shutdown with automatic recovery.
    """

    def __init__(self, resource_address: str = "TCPIP0::100.65.11.65::INSTR"):
        self.resource_address = resource_address
        self.inst: Optional[pyvisa.Resource] = None
        self.rm: Optional[pyvisa.ResourceManager] = None
        self.connected = False
        self.current_power: Optional[float] = None
        self.target_wavelength = 1500  # nm

    # ==================== Connection ====================

    def connect(self) -> bool:
        """Open VISA connection and verify identity."""
        try:
            self.rm = pyvisa.ResourceManager("visa32.dll")
            self.inst = self.rm.open_resource(self.resource_address)
            self.inst.timeout = 5000
            idn = self.inst.query("*IDN?").strip()
            print(f"[OK] Laser connected: {idn}")
            self.connected = True
            return True
        except Exception as e:
            print(f"[Error] Laser connection failed: {e}")
            self.connected = False
            return False

    def disconnect(self) -> None:
        """Close VISA session."""
        try:
            if self.inst:
                self.inst.close()
            if self.rm:
                self.rm.close()
        except Exception:
            pass
        self.connected = False

    def is_connected(self) -> bool:
        """Health check via *IDN? query."""
        if not self.inst or not self.connected:
            return False
        try:
            self.inst.query("*IDN?")
            return True
        except Exception:
            self.connected = False
            return False

    # ==================== Power control ====================

    def set_power(self, power_mw: float) -> bool:
        """Set laser output power in mW.

        power_mw == 0  →  output OFF only (keeps connection alive)
        power_mw  > 0  →  set power level and enable output
        """
        if not self.is_connected():
            print(f"[Warning] Laser not connected, skipping power set")
            return False

        try:
            if power_mw == 0:
                self.inst.write(":OUTPut:STATe OFF")
                self.current_power = 0
                print(f"[OK] Laser power → 0 mW (output OFF, connection kept)")
            else:
                self.inst.write(f":SOURce:POWer {power_mw}MW")
                self.inst.write(":OUTPut:STATe ON")
                self.current_power = power_mw
                print(f"[OK] Laser power → {power_mw} mW")
            return True
        except Exception as e:
            print(f"[Error] Failed to set laser power: {e}")
            return False

    def get_power(self) -> float:
        """Read current power setting (mW). Returns -1 on failure."""
        if not self.is_connected():
            return -1
        try:
            return float(self.inst.query(":SOURce:POWer?").strip())
        except Exception:
            return -1

    # ---- Backward-compatible aliases (for code that used KeysightLaser) ----

    def set_power_mw(self, power_mw: float) -> bool:
        """Alias for set_power()."""
        return self.set_power(power_mw)

    def output_on(self) -> None:
        """Turn laser output ON at whatever power was last set."""
        if self.inst:
            try:
                self.inst.write(":OUTPut:STATe ON")
            except Exception as e:
                print(f"[Error] output_on failed: {e}")

    def output_off(self) -> None:
        """Turn laser output OFF without changing power setting."""
        if self.inst:
            try:
                self.inst.write(":OUTPut:STATe OFF")
                self.current_power = 0
            except Exception as e:
                print(f"[Error] output_off failed: {e}")

    def close(self) -> None:
        """Alias for disconnect()."""
        self.disconnect()

    # ==================== Emergency shutdown ====================

    def physical_off(self) -> None:
        """Emergency: turn off output, then close VISA session.

        Use this only for emergency situations. Normal measurement
        pause should use set_power(0) instead.
        """
        print(f"[Warning] Executing physical laser shutdown...")
        try:
            if self.inst:
                self.inst.write(":OUTPut:STATe OFF")
                sleep(1)
                self.inst.close()
                self.inst = None
            self.connected = False
            self.current_power = None
            print(f"[OK] Laser physically turned off")
        except Exception as e:
            print(f"[Error] Physical shutdown failed: {e}")

    def physical_on(self) -> bool:
        """Re-power the laser after a physical_off().

        Reconnects and restores the target wavelength.
        """
        print(f"[Info] Attempting laser re-power...")
        if self.connect():
            self.set_wavelength(self.target_wavelength)
            print(f"[OK] Laser re-powered successfully")
            return True
        return False

    # ==================== Wavelength ====================

    def set_wavelength(self, wavelength_nm: float = 1500) -> bool:
        """Set laser wavelength in nm (default 1500)."""
        if not self.is_connected():
            return False
        try:
            self.inst.write(f":SOURce:WAV {wavelength_nm}NM")
            self.target_wavelength = wavelength_nm
            print(f"[OK] Laser wavelength → {wavelength_nm} nm")
            return True
        except Exception as e:
            print(f"[Error] Failed to set wavelength: {e}")
            return False

    def get_wavelength(self) -> float:
        """Read current wavelength (nm). Returns -1 on failure."""
        if not self.is_connected():
            return -1
        try:
            return float(self.inst.query(":SOURce:WAV?").strip())
        except Exception:
            return -1

    # ==================== Status ====================

    def get_status(self) -> dict:
        """Return full status dictionary."""
        status = {
            "connected": self.is_connected(),
            "power_mw": self.get_power() if self.is_connected() else None,
            "wavelength_nm": self.get_wavelength() if self.is_connected() else None,
            "output_enabled": False,
        }
        if self.is_connected():
            try:
                resp = self.inst.query(":OUTPut:STATe?").strip()
                status["output_enabled"] = resp == "1"
            except Exception:
                pass
        return status

    def print_status(self) -> None:
        """Pretty-print current status to console."""
        s = self.get_status()
        print("=" * 50)
        print("Laser Status:")
        print(f"  Connected:  {'YES' if s['connected'] else 'NO'}")
        if s["connected"]:
            print(f"  Power:      {s['power_mw']} mW")
            print(f"  Wavelength: {s['wavelength_nm']} nm")
            print(f"  Output:     {'ON' if s['output_enabled'] else 'OFF'}")
        print("=" * 50)

    # ==================== Reconnection recovery ====================

    def handle_disconnection(self) -> bool:
        """Multi-stage reconnection with staged back-off.

        Stage 1: 20s → 40s → 60s reconnect attempts
        Stage 2: Physical off + 30s wait, then retry 3× at 20s intervals

        Returns True if reconnection succeeded.
        """
        print("[Warning] Laser disconnection detected!")

        # Stage 1: normal reconnect
        for i, wait in enumerate([20, 40, 60]):
            print(f"[Info] Waiting {wait}s before retry ({i+1}/3)...")
            sleep(wait)
            if self.connect():
                print(f"[OK] Reconnected!")
                self.set_wavelength(self.target_wavelength)
                return True
            print(f"[Error] Retry {i+1} failed")

        # Stage 2: physical power cycle
        print("[Warning] All normal retries failed — physical shutdown...")
        self.physical_off()
        sleep(30)
        print(f"[Info] Attempting re-power...")
        if self.physical_on():
            print(f"[OK] Laser re-powered successfully")
            return True

        for i in range(3):
            print(f"[Info] Waiting 20s before detection ({i+1}/3)...")
            sleep(20)
            if self.connect():
                print(f"[OK] Reconnected!")
                self.set_wavelength(self.target_wavelength)
                return True
            print(f"[Error] Detection retry {i+1} failed")

        print("[Error] Laser recovery completely failed — manual intervention needed")
        return False
