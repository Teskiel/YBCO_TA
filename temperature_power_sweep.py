# -*- coding: utf-8 -*-
"""
Created on Tue Jun  2 15:44:48 2026

@author: DELL
"""

import os
import sys
from time import sleep, time

import pyvisa

from Lakeshore335 import LakeShore335


# ---------------------------
# 1. Instrument/resource setup
# ---------------------------

resource_vna = "TCPIP0::DESKTOP-1PLPGMT::hislip_PXI10_CHASSIS2_SLOT1_INDEX0::INSTR"
laser_resource = "TCPIP0::100.65.11.65::INSTR"
resource_lakeshore = "ASRL4::INSTR"

TRACE_NAME = "CH1_S21_1"

date = "20260529"
base_folder = rf"D:\YBCO\VNAMeas\data\{date}\-45dBm_temperature_sweep"
os.makedirs(base_folder, exist_ok=True)


# ---------------------------
# 2. Sweep settings
# ---------------------------

# Laser powers to sweep at each temperature, in mW.
# Use 0 to measure with the laser off.
power_levels_mw = [0, 1, 3, 5, 7, 9]

# Target temperature setpoints in K.
temperature_levels_k = range(24,80, 2)

# Wait until the measured temperature is within this tolerance of the setpoint.
temperature_tolerance_k = 0.10

# Temperature must stay inside tolerance for this many seconds before measuring.
stable_hold_seconds = 180

# Stop waiting for one setpoint after this many seconds.
max_wait_seconds = 30 * 60

# Polling interval while waiting for the cryostat to stabilize.
temperature_poll_seconds = 10


# ---------------------------
# 3. Laser control
# ---------------------------

class KeysightLaser:
    def __init__(self, resource_name):
        rm = pyvisa.ResourceManager()
        try:
            self.inst = rm.open_resource(resource_name)
            self.inst.timeout = 5000
            print("[OK] Laser connected:", self.inst.query("*IDN?").strip())
        except Exception as e:
            print(f"[Error] Laser connection failed: {e}")
            raise

    def set_power_mw(self, power_mw):
        self.inst.write(f":SOURce:POWer {power_mw}MW")

    def output_on(self):
        self.inst.write(":OUTPut:STATe ON")

    def output_off(self):
        self.inst.write(":OUTPut:STATe OFF")

    def close(self):
        self.inst.close()


# ---------------------------
# 4. LakeShore helpers
# ---------------------------

def configure_lakeshore_serial(temp_reader):
    if "ASRL" not in resource_lakeshore.upper():
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
    for attr in ["inst", "visa", "device", "ser", "com"]:
        if hasattr(temp_reader, attr):
            target = getattr(temp_reader, attr)
            if hasattr(target, "write"):
                return target
    return None


def set_lakeshore_temperature(temp_reader, target_k):
    """Set LakeShore output 1 setpoint, supporting several common driver styles."""
    method_names = [
        "set_temperature",
        "set_setpoint",
        "setpoint",
        "set_temperature_setpoint",
    ]

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
        raw.write(f"SETP 1,{target_k}")
        return

    raise AttributeError(
        "Could not find a LakeShore setpoint method or raw VISA handle. "
        "Edit set_lakeshore_temperature() to match your Lakeshore335 driver."
    )


def wait_for_temperature(temp_reader, target_k):
    stable_since = None
    start = time()

    while True:
        current_k = float(temp_reader.get_temperature())
        error_k = abs(current_k - target_k)
        elapsed = time() - start

        print(
            f"Target {target_k:.3f} K | current {current_k:.3f} K | "
            f"error {error_k:.3f} K | elapsed {elapsed / 60:.1f} min"
        )

        if error_k <= temperature_tolerance_k:
            if stable_since is None:
                stable_since = time()
            stable_time = time() - stable_since
            if stable_time >= stable_hold_seconds:
                return current_k
        else:
            stable_since = None

        if elapsed >= max_wait_seconds:
            print(
                f"[Warning] Max wait reached at target {target_k:.3f} K. "
                f"Continuing with current temperature {current_k:.3f} K."
            )
            return current_k

        sleep(temperature_poll_seconds)


def save_vna_s2p(vna, pc_filename):
    print("VNA single sweep starting...")
    vna.write(":INIT:CONT OFF")
    vna.write(":INIT:IMM")
    vna.query("*OPC?")

    vna_safe_path = pc_filename.replace("\\", "/")
    print(f"Saving S2P to: {vna_safe_path}")
    vna.write(f'MMEMory:STORe "{vna_safe_path}"')

    vna_msg = vna.query(":SYSTem:ERRor?").strip()
    print(f"[VNA status] {vna_msg}")


def set_laser_power(laser, power_mw, time_elaspe = 20):
    if power_mw == 0:
        laser.output_off()
        print("Laser output OFF for 0 mW measurement.")
        return

    laser.set_power_mw(power_mw)
    laser.output_on()
    print(f"Laser set to {power_mw} mW.")
    
    print(time_elaspe)
    sleep(time_elaspe)


# ---------------------------
# 5. Hardware initialization
# ---------------------------

print("=" * 40)
print("Starting hardware self-check")
print("=" * 40)

rm = pyvisa.ResourceManager("visa32.dll")

try:
    vna = rm.open_resource(resource_vna)
    vna.timeout = 120000
    print(f"[OK] Keysight VNA connected: {vna.query('*IDN?').strip()}")
except Exception as e:
    print(f"[Error] VNA connection failed: {e}")
    sys.exit(0)

laser = KeysightLaser(laser_resource)

temp_reader = LakeShore335(visa_address=resource_lakeshore)
configure_lakeshore_serial(temp_reader)

try:
    print(f"[OK] LakeShore335 initial temperature: {temp_reader.get_temperature()} K")
except Exception as e:
    print(f"[Warning] Initial temperature read failed: {e}")


# ---------------------------
# 6. Temperature and laser-power sweep
# ---------------------------

count = 0
print("\n" + "-" * 10 + " Starting temperature and laser-power sweep " + "-" * 10)

sleep_time = 20;

#try:
for target_temp_k in temperature_levels_k:
        print(f"\n>>> Preparing measurement at {target_temp_k} K")

        set_lakeshore_temperature(temp_reader, target_temp_k)
        current_temp_k = wait_for_temperature(temp_reader, target_temp_k)

        target_temp_str = f"{target_temp_k:g}K"

        for power_mw in power_levels_mw:
            print(f"\n>>> Measuring {power_mw} mW at target {target_temp_str}")
            
            current_temp_k = float(temp_reader.get_temperature())
            
            set_laser_power(laser, power_mw, sleep_time)

            power_str = f"{power_mw:02d}"
            folder_data = os.path.join(
                base_folder,
                target_temp_str,
                f"{power_str}mW",
            )
            os.makedirs(folder_data, exist_ok=True)

            filename = f"YBCO_{power_str}mW_target_{target_temp_str}_actual_{current_temp_k:.3f}K.s2p"
            pc_filename = os.path.join(folder_data, filename)

            save_vna_s2p(vna, pc_filename)
            count += 1

#except Exception as main_err:
#    print(f"\n[System Error] Runtime exception: {main_err}")

#finally:
#    print("\n" + "=" * 40)
#    print("Safely closing devices...")
#    print("=" * 40)
#    try:
#        laser.output_off()
#        laser.close()
#        vna.close()
#    except Exception as e:
#        print(f"Resource close warning: {e}")
#    print("Temperature sweep script exited safely.")
