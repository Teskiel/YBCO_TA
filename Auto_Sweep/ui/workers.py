# -*- coding: utf-8 -*-
"""
Background worker objects for instrument VISA communication.

Each worker lives on its own QThread.  All VISA calls happen off the
UI thread so the GUI never freezes.  Results are delivered back via
pyqtSignals.

Pattern based on DeviceWorker in Lakeshore335_output.py.
"""

from dataclasses import dataclass
from typing import Optional

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class LakeShoreReading:
    temperature_a: Optional[float] = None
    temperature_b: Optional[float] = None
    heater_1: Optional[float] = None
    heater_2: Optional[float] = None
    setpoint_1: Optional[float] = None
    setpoint_2: Optional[float] = None
    range_1: Optional[int] = None
    range_2: Optional[int] = None
    pid_p1: Optional[float] = None
    pid_i1: Optional[float] = None
    pid_d1: Optional[float] = None
    pid_p2: Optional[float] = None
    pid_i2: Optional[float] = None
    pid_d2: Optional[float] = None


# ---------------------------------------------------------------------------
# LaserWorker
# ---------------------------------------------------------------------------

class LaserWorker(QObject):
    connected = pyqtSignal(str)       # identity string
    disconnected = pyqtSignal()
    status_updated = pyqtSignal(dict) # full status dict
    error = pyqtSignal(str)
    log = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._laser = None

    @pyqtSlot(str)
    def connect_device(self, address: str):
        try:
            from laser_driver import LaserController
            self._laser = LaserController(address)
            ok = self._laser.connect()
            if ok:
                status = self._laser.get_status()
                self.connected.emit(self._laser.inst.query("*IDN?").strip() if self._laser.inst else "Laser")
                self.status_updated.emit(status)
                self.log.emit(f"Laser connected: {address}")
            else:
                self.error.emit(f"Laser connection failed: {address}")
        except Exception as e:
            self._laser = None
            self.error.emit(f"Laser connection error: {e}")

    @pyqtSlot()
    def disconnect_device(self):
        if self._laser:
            try:
                self._laser.disconnect()
            except Exception as e:
                self.error.emit(f"Laser disconnect error: {e}")
        self._laser = None
        self.disconnected.emit()
        self.log.emit("Laser disconnected")

    @pyqtSlot(float)
    def set_power(self, power_mw: float):
        if not self._laser:
            self.error.emit("Laser not connected")
            return
        try:
            self._laser.set_power(power_mw)
            self.status_updated.emit(self._laser.get_status())
            self.log.emit(f"Laser power → {power_mw} mW")
        except Exception as e:
            self.error.emit(f"Laser set_power error: {e}")

    @pyqtSlot(float)
    def set_wavelength(self, nm: float):
        if not self._laser:
            self.error.emit("Laser not connected")
            return
        try:
            self._laser.set_wavelength(nm)
            self.status_updated.emit(self._laser.get_status())
            self.log.emit(f"Laser wavelength → {nm} nm")
        except Exception as e:
            self.error.emit(f"Laser set_wavelength error: {e}")

    @pyqtSlot()
    def output_on(self):
        if self._laser:
            self._laser.output_on()
            self.status_updated.emit(self._laser.get_status())

    @pyqtSlot()
    def output_off(self):
        if self._laser:
            self._laser.output_off()
            self.status_updated.emit(self._laser.get_status())

    @pyqtSlot()
    def physical_off(self):
        if self._laser:
            self._laser.physical_off()
            self.status_updated.emit(self._laser.get_status())
            self.log.emit("Laser physically OFF")

    @pyqtSlot()
    def refresh_status(self):
        if self._laser:
            try:
                self.status_updated.emit(self._laser.get_status())
            except Exception as e:
                self.error.emit(f"Laser status read error: {e}")


# ---------------------------------------------------------------------------
# LakeShoreWorker
# ---------------------------------------------------------------------------

class LakeShoreWorker(QObject):
    connected = pyqtSignal(str)
    disconnected = pyqtSignal()
    reading = pyqtSignal(object)     # LakeShoreReading
    error = pyqtSignal(str)
    log = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._controller = None

    @pyqtSlot(str)
    def connect_device(self, address: str):
        try:
            from lakeshore_control import LakeShore335
            self._controller = LakeShore335(address)
            self.connected.emit(self._controller.identity)
            self.log.emit(f"LakeShore connected: {self._controller.identity}")
        except Exception as e:
            self._controller = None
            self.error.emit(f"LakeShore connection failed: {e}")

    @pyqtSlot()
    def disconnect_device(self):
        if self._controller:
            try:
                self._controller.close()
            except Exception as e:
                self.error.emit(f"LakeShore disconnect error: {e}")
        self._controller = None
        self.disconnected.emit()
        self.log.emit("LakeShore disconnected")

    @pyqtSlot()
    def poll(self):
        """Read all live values. Called by a 1-second QTimer."""
        if self._controller is None:
            return
        try:
            pid1 = self._controller.get_pid(1)
            pid2 = self._controller.get_pid(2)
            r = LakeShoreReading(
                temperature_a=self._controller.get_temperature("A"),
                temperature_b=self._controller.get_temperature("B"),
                heater_1=self._controller.get_heater_percent(1),
                heater_2=self._controller.get_heater_percent(2),
                setpoint_1=self._controller.get_setpoint(1),
                setpoint_2=self._controller.get_setpoint(2),
                range_1=self._controller.get_heater_range(1),
                range_2=self._controller.get_heater_range(2),
                pid_p1=pid1[0], pid_i1=pid1[1], pid_d1=pid1[2],
                pid_p2=pid2[0], pid_i2=pid2[1], pid_d2=pid2[2],
            )
            self.reading.emit(r)
        except Exception as e:
            self.error.emit(f"LakeShore poll error: {e}")

    @pyqtSlot(int, float)
    def set_setpoint(self, loop: int, kelvin: float):
        """Set temperature setpoint with cooling-safety interlock.

        Four temperature parameters (see CLAUDE.md):
          - actual_temp    = ``KRDG? A`` (or B) — real sample temperature
          - target_sp      = value written to ``SETP {loop},{kelvin}``
          - (ramp rate means the internal setpoint ramps slowly toward target_sp)

        Safety rule (one-directional — only intervenes when "too hot"):
          If actual_temp > target_sp + 20 K → heater OFF,
          poll until actual_temp - target_sp < 20 K,
          then heater → Medium, then write SETP.
        """
        if not self._controller:
            self.error.emit("LakeShore not connected")
            return
        try:
            channel = "A" if loop == 1 else "B"
            actual = self._controller.get_temperature(channel)

            if actual > kelvin + 20.0:
                diff = actual - kelvin
                self.log.emit(
                    f"Loop {loop}: actual ({actual:.2f} K) is "
                    f"{diff:.1f} K above target ({kelvin:.2f} K). "
                    f"Turning heater OFF for cooldown safety..."
                )
                self._controller.set_heater_range(loop, 0)  # OFF

                import time
                timeout_s = 600  # 10-minute safety timeout
                started = time.time()
                while True:
                    if time.time() - started > timeout_s:
                        self.error.emit(
                            f"Loop {loop}: cooldown safety timeout "
                            f"(waited {timeout_s}s, actual still "
                            f"{actual:.2f} K, target {kelvin:.2f} K)")
                        return
                    time.sleep(2)
                    try:
                        actual = self._controller.get_temperature(channel)
                    except Exception:
                        continue
                    if actual - kelvin < 20.0:
                        break

                self.log.emit(
                    f"Loop {loop}: actual ({actual:.2f} K) now within "
                    f"20 K of target ({kelvin:.2f} K). "
                    f"Setting heater to Medium."
                )
                self._controller.set_heater_range(loop, 2)  # Medium

            self._controller.set_temperature(kelvin, loop)
            self.log.emit(f"Loop {loop} setpoint → {kelvin:.4f} K")
        except Exception as e:
            self.error.emit(f"LakeShore setpoint error: {e}")

    @pyqtSlot(int, int)
    def set_heater_range(self, output: int, range_level: int):
        """设置加热器档位。一律强制使用 Medium (2)。"""
        if not self._controller:
            self.error.emit("LakeShore not connected")
            return
        try:
            # 一律使用 Medium (2)，忽略传入的 range_level
            self._controller.set_heater_range(output, 2)
            self.log.emit(f"Output {output} heater range → Medium (2)")
        except Exception as e:
            self.error.emit(f"LakeShore heater range error: {e}")

    @pyqtSlot(int, float, float, float)
    def set_pid(self, loop: int, p: float, i: float, d: float):
        if not self._controller:
            self.error.emit("LakeShore not connected")
            return
        try:
            self._controller.set_pid(p, i, d, loop)
            self.log.emit(f"Loop {loop} PID → P={p:g}, I={i:g}, D={d:g}")
        except Exception as e:
            self.error.emit(f"LakeShore PID error: {e}")

    @pyqtSlot(int)
    def read_pid(self, loop: int):
        if not self._controller:
            self.error.emit("LakeShore not connected")
            return
        try:
            p, i, d = self._controller.get_pid(loop)
            self.log.emit(f"Loop {loop} PID readback: P={p:g}, I={i:g}, D={d:g}")
        except Exception as e:
            self.error.emit(f"LakeShore PID read error: {e}")

    @pyqtSlot()
    def all_heaters_off(self):
        if not self._controller:
            self.error.emit("LakeShore not connected")
            return
        try:
            self._controller.all_heaters_off()
            self.log.emit("ALL HEATERS OFF")
        except Exception as e:
            self.error.emit(f"LakeShore all-off error: {e}")


# ---------------------------------------------------------------------------
# VNAWorker (Keysight P5003A via HiSLIP)
# ---------------------------------------------------------------------------

class VNAWorker(QObject):
    connected = pyqtSignal(str)
    disconnected = pyqtSignal()
    settings_applied = pyqtSignal(dict)   # echo of applied settings
    error = pyqtSignal(str)
    log = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._vna = None
        self._rm = None           # keep ResourceManager alive

    # ---- connection -------------------------------------------------

    @pyqtSlot(str)
    def connect_device(self, address: str):
        try:
            import pyvisa
            self._rm = pyvisa.ResourceManager("visa32.dll")
            self._vna = self._rm.open_resource(address)
            self._vna.timeout = 120000
            idn = self._vna.query("*IDN?").strip()
            self.connected.emit(idn)
            self.log.emit(f"VNA connected: {idn}")
        except Exception as e:
            self._vna = None
            self._rm = None
            self.error.emit(f"VNA connection failed: {e}")

    @pyqtSlot()
    def disconnect_device(self):
        if self._vna:
            try:
                self._vna.close()
            except Exception:
                pass
        if self._rm:
            try:
                self._rm.close()
            except Exception:
                pass
        self._vna = None
        self._rm = None
        self.disconnected.emit()
        self.log.emit("VNA disconnected")

    # ---- all-settings apply -----------------------------------------

    @pyqtSlot(dict)
    def apply_settings(self, settings: dict):
        """Apply all VNA settings from a dict.

        Keys: start_freq_hz, stop_freq_hz, s_parameter, power_dbm,
              points, if_bandwidth_hz
        """
        if not self._vna:
            self.error.emit("VNA not connected")
            return
        try:
            # frequency range — set start then stop
            if "start_freq_hz" in settings:
                self._vna.write(f":SENSe:FREQuency:STARt {settings['start_freq_hz']:.0f}")
            if "stop_freq_hz" in settings:
                self._vna.write(f":SENSe:FREQuency:STOP {settings['stop_freq_hz']:.0f}")

            # S-parameter
            if "s_parameter" in settings:
                sp = settings["s_parameter"]
                self._vna.write(f':CALCulate:PARameter:DELete:ALL')
                self._vna.write(f':CALCulate:PARameter:DEFine:EXTended "{sp}","{sp}"')
                self._vna.write(f':DISPlay:WINDow1:TRACe1:FEED "{sp}"')

            # power
            if "power_dbm" in settings:
                pwr = settings["power_dbm"]
                if isinstance(pwr, list):
                    pwr = pwr[0] if pwr else -45
                self._vna.write(f":SOURce:POWer {pwr}")

            # points
            if "points" in settings:
                self._vna.write(f":SENSe:SWEep:POINts {settings['points']}")

            # IF bandwidth
            if "if_bandwidth_hz" in settings:
                self._vna.write(f":SENSe:BANDwidth {settings['if_bandwidth_hz']}")

            self.settings_applied.emit(settings)
            self.log.emit(f"VNA settings applied: "
                          f"{settings.get('start_freq_hz',0)/1e9:.1f}–"
                          f"{settings.get('stop_freq_hz',0)/1e9:.1f} GHz, "
                          f"{settings.get('s_parameter','?')}, "
                          f"{settings.get('points','?')} pts, "
                          f"IFBW {settings.get('if_bandwidth_hz','?')} Hz")
        except Exception as e:
            self.error.emit(f"VNA apply_settings error: {e}")

    # ---- single sweep + save S2P -----------------------------------

    @pyqtSlot(str)
    def single_sweep(self, save_path: str):
        """Trigger a single sweep and save the result as .s2p."""
        if not self._vna:
            self.error.emit("VNA not connected")
            return
        try:
            from time import sleep
            vna_safe_path = save_path.replace("\\", "/")
            self._vna.write(":INITiate:CONTinuous OFF")
            self._vna.write(":INITiate:IMMediate")
            try:
                self._vna.query("*OPC?")
            except Exception:
                sleep(5)

            self._vna.write(f'MMEMory:STORe "{vna_safe_path}"')
            try:
                msg = self._vna.query(":SYSTem:ERRor?").strip()
                self.log.emit(f"VNA sweep saved: {vna_safe_path}  [{msg}]")
            except Exception:
                self.log.emit(f"VNA sweep saved: {vna_safe_path}")
        except Exception as e:
            self.error.emit(f"VNA sweep error: {e}")


# ---------------------------------------------------------------------------
# ExperimentWorker — full YBCO temperature + laser power sweep
# ---------------------------------------------------------------------------

class ExperimentWorker(QObject):
    """Runs the temperature-and-power sweep experiment on a background thread.

    Uses direct controller references (not signals) for synchronous flow:
    stabilise temperature → sweep power levels → save S2P → next temp.

    Signals report progress back to the UI thread.
    """

    experiment_started = pyqtSignal()
    progress = pyqtSignal(str)
    temperature_stabilizing = pyqtSignal(float, float)       # target_k, actual_k
    temperature_stable = pyqtSignal(float, float)             # target_k, actual_k
    measurement_started = pyqtSignal(float, float)            # temp_k, power_mw
    measurement_complete = pyqtSignal(float, float, str)      # temp_k, power_mw, filepath
    experiment_finished = pyqtSignal(int)                     # total count
    experiment_error = pyqtSignal(str)
    experiment_aborted = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._abort_flag = False
        self._lakeshore_ctrl = None
        self._laser_ctrl = None
        self._vna = None
        self._temp_list = []
        self._power_list = []
        self._vna_power_list = []
        self._output_dir = ""
        self._vna_settings = {}

    def configure(
        self,
        *,
        lakeshore_ctrl=None,
        laser_ctrl=None,
        vna_resource=None,
        temp_list=None,
        power_list=None,
        vna_power_list=None,
        output_dir="",
        vna_settings=None,
    ):
        self._lakeshore_ctrl = lakeshore_ctrl
        self._laser_ctrl = laser_ctrl
        self._vna = vna_resource
        self._temp_list = list(temp_list or [])
        self._power_list = list(power_list or [])
        self._vna_power_list = list(vna_power_list or [])
        self._output_dir = output_dir
        self._vna_settings = dict(vna_settings or {})
        self._abort_flag = False

    @pyqtSlot()
    def abort(self):
        self._abort_flag = True
        self.progress.emit("Abort requested — finishing current step...")

    def _apply_setpoint_adjustment(self, new_setpoint: float, overshoot: float,
                                     base_overshoot: float, actual_k: float = 0):
        """将新的设定点写入 LakeShore（仅调整设定点，不修改 PID）。

        包含基本安全保护：大温差时发出警告。

        Args:
            new_setpoint: 新设定点温度 (K)
            overshoot: 当前过冲量 (K)
            base_overshoot: 基础过冲量 (K)
            actual_k: 当前实际温度 (K)，用于安全检查
        """
        if not self._lakeshore_ctrl:
            return

        # 安全检查：实际温度远高于设定点时发出警告
        if actual_k > 0 and actual_k > new_setpoint + 30.0:
            self.progress.emit(
                f"  ⚠ 安全警告: 实际温度 {actual_k:.1f}K 比设定点 "
                f"{new_setpoint:.1f}K 高 {actual_k - new_setpoint:.0f}K，"
                f"建议先自然冷却")

        try:
            self._lakeshore_ctrl.set_temperature(new_setpoint, loop=1)
            extra = overshoot - base_overshoot
            if extra > 0.01:
                self.progress.emit(
                    f"  设定点过冲调整 → {new_setpoint:.3f} K "
                    f"(base +{base_overshoot:.1f}K + Δ{extra:.1f}K)")
            elif overshoot > 0.01:
                self.progress.emit(
                    f"  初始设定点 → {new_setpoint:.3f} K "
                    f"(overshoot +{overshoot:.1f}K)")
            else:
                self.progress.emit(
                    f"  设定点 → {new_setpoint:.3f} K (无过冲)")
        except Exception as e:
            self.progress.emit(f"  设定点写入失败: {e}")

    # ------------------------------------------------------------------
    # 测量时温度监控
    # ------------------------------------------------------------------

    @staticmethod
    def _check_measurement_temp(pre_k: float, post_k: float,
                                 target_k: float) -> tuple:
        """检查测量前后的温度是否满足稳态条件。

        Args:
            pre_k: 测量前实际温度 (K)
            post_k: 测量后实际温度 (K)
            target_k: 目标温度 (K)

        Returns:
            (ok: bool, reason: str)
        """
        # 测量前温度偏离 > ±0.5K
        if abs(pre_k - target_k) > 0.5:
            return (False,
                    f"测量前温度偏离: {pre_k:.3f}K vs target {target_k:.1f}K "
                    f"(Δ={abs(pre_k-target_k):.3f}K > 0.5K)")

        # 测量后温度偏离 > ±0.5K
        if abs(post_k - target_k) > 0.5:
            return (False,
                    f"测量后温度偏离: {post_k:.3f}K vs target {target_k:.1f}K "
                    f"(Δ={abs(post_k-target_k):.3f}K > 0.5K)")

        # 测量期间温度跳变 > 0.3K
        delta = abs(post_k - pre_k)
        if delta > 0.3:
            return (False,
                    f"测量期间温度跳变: |{post_k:.3f} - {pre_k:.3f}|"
                    f" = {delta:.3f}K > 0.3K")

        return (True, "")

    # ------------------------------------------------------------------
    # 实验主循环
    # ------------------------------------------------------------------

    @pyqtSlot()
    def run(self):
        try:
            from datetime import datetime
            import time as _time
            import os
            import config

            self.experiment_started.emit()
            count = 0
            start_time = datetime.now()

            # ---- 创建日志目录并打开日志文件 ----
            log_dir = os.path.join(self._output_dir, "logs")
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(
                log_dir,
                f"experiment_log_{start_time.strftime('%Y%m%d_%H%M%S')}.txt")

            # 先定义 _log（使用临时占位，稍后替换为真实文件）
            def _log_fallback(msg: str):
                self.progress.emit(msg)

            def _log(msg: str):
                """同时写入 GUI 信号和日志文件。"""
                ts = _time.strftime(
                    "[%Y-%m-%d %H:%M:%S] ", _time.localtime(_time.time()))
                self.progress.emit(msg)
                log_file.write(ts + msg + "\n")
                log_file.flush()

            try:
                log_file = open(log_path, "w", encoding="utf-8")
            except (OSError, IOError) as _log_open_err:
                import io
                log_file = io.StringIO()
                self.progress.emit(
                    f"  ⚠ 无法创建日志文件: {_log_open_err}，使用内存缓冲")

            _log(f"实验开始 — 输出目录: {self._output_dir}")
            _log(f"温度列表: {self._temp_list}")
            _log(f"激光功率列表: {self._power_list} mW")
            _log(f"VNA 功率列表: {self._vna_power_list} dBm")

            for target_k in self._temp_list:
                if self._abort_flag:
                    self.experiment_aborted.emit()
                    log_file.close()
                    return

                _log(f"→ Stabilising to {target_k:.1f} K ...")

                # ---- 读取当前温度 ----
                actual_k = target_k
                try:
                    if self._lakeshore_ctrl:
                        actual_k = self._lakeshore_ctrl.get_temperature("A")
                        if actual_k is None:
                            actual_k = target_k
                except Exception as e:
                    _log(f"  ⚠ 初始温度读取失败: {e}，使用 target={target_k:.1f}K 作为回退")

                # ---- 初始化稳定性控制器 ----
                from ui.experiment_stability_controller import (
                    ExperimentStabilityController,
                )
                stability_ctrl = ExperimentStabilityController()
                stability_ctrl.setup(
                    target_k=target_k,
                    current_temperature=actual_k,
                )

                # ---- 确保加热器在 Medium 档位 ----
                if self._lakeshore_ctrl:
                    self._lakeshore_ctrl.set_heater_range(1, 2)

                # ---- 写入固定 PID（仅一次，永不调整） ----
                fixed_pid = stability_ctrl.get_fixed_pid()
                if self._lakeshore_ctrl:
                    self._lakeshore_ctrl.set_pid(
                        fixed_pid["p"], fixed_pid["i"], fixed_pid["d"], loop=1)

                # ---- 写入初始设定点 ----
                setpoint_k = stability_ctrl.needs_setpoint_adjustment()
                if self._lakeshore_ctrl and setpoint_k is not None:
                    self._lakeshore_ctrl.set_temperature(setpoint_k, loop=1)
                    overshoot_info = ""
                    if stability_ctrl.current_overshoot > 0.01:
                        overshoot_info = f" (overshoot +{stability_ctrl.current_overshoot:.1f}K)"
                    _log(f"  温区 PID: P={fixed_pid['p']:g}/"
                         f"I={fixed_pid['i']:g}/D={fixed_pid['d']:g}, "
                         f"设定点 → {setpoint_k:.3f} K{overshoot_info}")

                # ---- 等待稳定性（2 阶段轮询） ----
                start_t = _time.time()
                prev_phase = "sparse"

                while True:
                    if self._abort_flag:
                        self.experiment_aborted.emit()
                        log_file.close()
                        return

                    # 读取温度
                    try:
                        actual_k = self._lakeshore_ctrl.get_temperature("A") \
                            if self._lakeshore_ctrl else target_k
                    except Exception:
                        _time.sleep(10)
                        continue

                    if actual_k is None:
                        actual_k = target_k

                    # 添加到稳定性控制器
                    stability_ctrl.add_reading(actual_k)
                    self.temperature_stabilizing.emit(target_k, actual_k)

                    elapsed = _time.time() - start_t
                    result = stability_ctrl.check(elapsed)

                    # 阶段转换日志
                    if stability_ctrl.phase.value != prev_phase:
                        prev_phase = stability_ctrl.phase.value
                        if prev_phase == "fine":
                            _log(f"  进入 Phase 2（趋于平稳），提高轮询频率至 "
                                 f"{config.fine_poll_seconds}s，并行判目标区间+稳态")

                    # 检查是否需要调整设定点过冲
                    new_sp = stability_ctrl.needs_setpoint_adjustment()
                    if new_sp is not None:
                        self._apply_setpoint_adjustment(
                            new_sp,
                            stability_ctrl.current_overshoot,
                            stability_ctrl.base_overshoot,
                            actual_k,
                        )

                    # 处理结果
                    if result.stable:
                        self.temperature_stable.emit(target_k, actual_k)
                        _log(f"  稳定: {actual_k:.3f} K "
                             f"(target {target_k:.1f} K, "
                             f"phase={stability_ctrl.phase.value})")
                        break
                    elif result.reason == "good_enough":
                        _log(f"  good_enough — "
                             f"avg={result.avg_temp:.3f}K vs "
                             f"target={target_k:.1f}K "
                             f"(phase={stability_ctrl.phase.value})，继续测量")
                        self.temperature_stable.emit(target_k, actual_k)
                        break
                    elif result.reason == "timeout":
                        _log(f"  Timeout at {target_k:.1f}K — "
                             f"avg={result.avg_temp:.3f}K, "
                             f"Δ={abs(result.avg_temp - target_k):.3f}K")
                        self.temperature_stable.emit(target_k, actual_k)
                        break

                    # 阶段感知轮询间隔
                    poll_s = (config.fine_poll_seconds
                              if stability_ctrl.phase.value == "fine"
                              else config.sparse_poll_seconds)
                    _time.sleep(poll_s)

                # ============================================================
                # VNA power sweep + laser power sweep（含测量时温度监控）
                # ============================================================
                MAX_MEASUREMENT_RESTARTS = 3  # 单个温度点最多重启测量次数

                # 确保至少有一个 VNA 功率值
                vna_powers = list(self._vna_power_list) if self._vna_power_list else []
                if not vna_powers:
                    fallback = self._vna_settings.get("power_dbm", [-45])
                    if isinstance(fallback, list):
                        vna_powers = list(fallback)
                    else:
                        vna_powers = [fallback]
                vna_powers = sorted(set(vna_powers))

                # 测量重启循环
                measurement_restarts = 0
                while True:
                    measurement_ok = True
                    deleted_any = False

                    # Apply VNA freq + S-param once per restart
                    if self._vna and self._vna_settings:
                        vs = self._vna_settings
                        self._vna.write(
                            f":SENSe:FREQuency:STARt "
                            f"{vs.get('start_freq_hz', 3e9):.0f}")
                        self._vna.write(
                            f":SENSe:FREQuency:STOP "
                            f"{vs.get('stop_freq_hz', 6e9):.0f}")
                        if vs.get("s_parameter"):
                            sp = vs["s_parameter"]
                            self._vna.write(
                                f':CALCulate:PARameter:DELete:ALL')
                            self._vna.write(
                                f':CALCulate:PARameter:DEFine:EXTended '
                                f'"{sp}","{sp}"')
                            self._vna.write(
                                f':DISPlay:WINDow1:TRACe1:FEED "{sp}"')

                    for vna_dbm in vna_powers:
                        if self._abort_flag or not measurement_ok:
                            break

                        # set VNA source power
                        if self._vna:
                            self._vna.write(f":SOURce:POWer {vna_dbm}")

                        for power_mw in self._power_list:
                            if self._abort_flag:
                                self.experiment_aborted.emit()
                                log_file.close()
                                return

                            # ---- 测量前读取温度 ----
                            pre_temp = actual_k
                            try:
                                if self._lakeshore_ctrl:
                                    t = self._lakeshore_ctrl.get_temperature("A")
                                    if t is not None:
                                        pre_temp = t
                            except Exception:
                                pass

                            self.measurement_started.emit(pre_temp, power_mw)
                            _log(f"  Measuring {vna_dbm:+d} dBm / "
                                 f"{power_mw} mW @ {pre_temp:.3f} K")

                            # apply laser
                            if self._laser_ctrl:
                                if power_mw == 0:
                                    self._laser_ctrl.output_off()
                                else:
                                    self._laser_ctrl.set_power(power_mw)
                                    self._laser_ctrl.output_on()
                                _time.sleep(20)  # optical settle

                            # ---- 输出路径 ----
                            temp_str = f"{target_k:.0f}K"
                            folder = os.path.join(
                                self._output_dir, temp_str,
                                f"{vna_dbm:+d}dBm",
                                f"{power_mw:02d}mW")
                            os.makedirs(folder, exist_ok=True)
                            filename = (
                                f"YBCO_{vna_dbm:+d}dBm_"
                                f"{power_mw:02d}mW_target_{temp_str}"
                                f"_actual_{pre_temp:.3f}K.s2p")
                            filepath = os.path.join(folder, filename)

                            # sweep + save S2P
                            if self._vna:
                                vna_safe = filepath.replace("\\", "/")
                                self._vna.write(":INITiate:CONTinuous OFF")
                                self._vna.write(":INITiate:IMMediate")
                                try:
                                    self._vna.query("*OPC?")
                                except Exception:
                                    _time.sleep(5)
                                self._vna.write(
                                    f'MMEMory:STORe "{vna_safe}"')
                                count += 1

                            # ---- 测量后读取温度 ----
                            post_temp = pre_temp
                            try:
                                if self._lakeshore_ctrl:
                                    t = self._lakeshore_ctrl.get_temperature("A")
                                    if t is not None:
                                        post_temp = t
                            except Exception:
                                pass

                            # ---- 测量时温度监控 ----
                            temp_ok, temp_reason = self._check_measurement_temp(
                                pre_temp, post_temp, target_k)

                            if not temp_ok:
                                _log(f"  ⚠ 测量温度异常: {temp_reason}")
                                # 删除异常数据文件
                                try:
                                    if os.path.exists(filepath):
                                        os.remove(filepath)
                                        _log(f"  已删除异常数据: {filename}")
                                except Exception as e:
                                    _log(f"  删除文件失败: {e}")

                                count -= 1
                                measurement_ok = False
                                deleted_any = True
                                break  # 跳出功率循环

                            self.measurement_complete.emit(
                                post_temp, power_mw, filepath)
                            # 更新 actual_k 为最新温度
                            actual_k = post_temp

                        if not measurement_ok:
                            break  # 跳出 VNA 功率循环

                    if measurement_ok:
                        # 测量全部通过
                        break

                    # ---- 测量异常 → 重启稳定性 ----
                    measurement_restarts += 1
                    _log(f"  ⚠ 测量重启 #{measurement_restarts}"
                         f"/{MAX_MEASUREMENT_RESTARTS} — 重新等待温度稳定")

                    if measurement_restarts >= MAX_MEASUREMENT_RESTARTS:
                        _log(f"  ⚠ 已达最大测量重启次数"
                             f"({MAX_MEASUREMENT_RESTARTS})，"
                             f"以 good_enough 模式继续")
                        break

                    # 重新等待稳定性
                    stability_ctrl.setup(
                        target_k=target_k,
                        current_temperature=actual_k,
                    )
                    if self._lakeshore_ctrl:
                        new_fixed_pid = stability_ctrl.get_fixed_pid()
                        self._lakeshore_ctrl.set_pid(
                            new_fixed_pid["p"], new_fixed_pid["i"],
                            new_fixed_pid["d"], loop=1)
                        new_sp = stability_ctrl.needs_setpoint_adjustment()
                        if new_sp is not None:
                            self._lakeshore_ctrl.set_temperature(new_sp, loop=1)

                    restart_start = _time.time()
                    while True:
                        if self._abort_flag:
                            self.experiment_aborted.emit()
                            log_file.close()
                            return
                        try:
                            actual_k = self._lakeshore_ctrl.get_temperature("A") \
                                if self._lakeshore_ctrl else target_k
                        except Exception:
                            _time.sleep(10)
                            continue
                        if actual_k is None:
                            actual_k = target_k

                        stability_ctrl.add_reading(actual_k)
                        self.temperature_stabilizing.emit(target_k, actual_k)

                        elapsed = _time.time() - restart_start
                        result = stability_ctrl.check(elapsed)

                        new_sp = stability_ctrl.needs_setpoint_adjustment()
                        if new_sp is not None:
                            self._apply_setpoint_adjustment(
                                new_sp,
                                stability_ctrl.current_overshoot,
                                stability_ctrl.base_overshoot,
                                actual_k,
                            )

                        if result.stable or result.reason == "good_enough":
                            _log(f"  重启后稳定: {actual_k:.3f} K")
                            self.temperature_stable.emit(target_k, actual_k)
                            break
                        elif result.reason == "timeout":
                            _log(f"  重启超时 — 以 good_enough 模式继续")
                            break

                        poll_s = (config.fine_poll_seconds
                                  if stability_ctrl.phase.value == "fine"
                                  else config.sparse_poll_seconds)
                        _time.sleep(poll_s)

                # 切换到下一个温度点前：激光功率归零
                if self._laser_ctrl:
                    self._laser_ctrl.set_power(0)
                    self._laser_ctrl.output_off()
                    _log(f"  温度点完成，激光功率 → 0 mW（准备升温）")

            # ================================================================
            # 实验完成 — 生成 readme.txt
            # ================================================================
            end_time = datetime.now()
            _log(f"Experiment complete — {count} measurements")

            try:
                from readme_generator import generate_readme
                import config

                # 收集设备参数
                laser_params = {
                    "wavelength_nm": self._vna_settings.get("laser_wavelength_nm",
                        getattr(self._laser_ctrl, "_wavelength", None) or 1550.0),
                    "power_sequence_mw": self._power_list,
                }
                lakeshore_params = {
                    "setpoint_k": self._temp_list[0] if self._temp_list else "—",
                    "pid": fixed_pid if 'fixed_pid' in dir() else {},
                    "heater_range": 2,
                }
                vna_info = dict(self._vna_settings)
                vna_info["address"] = getattr(
                    self._vna, "_resource_name", "—") if self._vna else "—"

                readme_path = generate_readme(
                    output_dir=self._output_dir,
                    start_time=start_time,
                    end_time=end_time,
                    laser_params=laser_params,
                    lakeshore_params=lakeshore_params,
                    vna_params=vna_info,
                    measurement_count=count,
                    measurement_logic_version=getattr(
                        config, "MEASUREMENT_LOGIC_VERSION", ""),
                )
                _log(f"readme.txt generated: {readme_path}")
            except Exception as e:
                _log(f"⚠ readme.txt 生成失败: {e}")

            _log(f"日志文件: {log_path}")
            log_file.close()
            self.experiment_finished.emit(count)

        except Exception as e:
            self.experiment_error.emit(f"Experiment failed: {e}")
            try:
                log_file.close()
            except Exception:
                pass
