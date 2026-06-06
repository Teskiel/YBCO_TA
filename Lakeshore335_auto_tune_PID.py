# -*- coding: utf-8 -*-
"""
Created on Wed Jun  3 18:01:12 2026

@author: DELL
"""

# -*- coding: utf-8 -*-
"""
Created on Mon May 11 14:36:16 2026

@author: DELL
"""

"""
PyQt control panel for a Lake Shore Model 335 Temperature Controller.

Requirements:
    pip install pyqt5 pyvisa pyvisa-py

Run:
    python lakeshore335_pyqt_control.py

Typical VISA addresses:
    USB virtual COM on Windows: ASRL3::INSTR, ASRL4::INSTR, ...
    GPIB: GPIB0::12::INSTR or GPIB::12::INSTR
"""
"""
PyQt control panel for a Lake Shore Model 335 Temperature Controller.

Requirements:
    pip install pyqt5 pyvisa pyvisa-py

Run:
    python lakeshore335_pyqt_control.py

Typical VISA addresses:
    USB virtual COM on Windows: ASRL3::INSTR, ASRL4::INSTR, ...
    GPIB: GPIB0::12::INSTR or GPIB::12::INSTR
"""
"""
PyQt control panel for a Lake Shore Model 335 Temperature Controller.

Requirements:
    pip install pyqt5 pyvisa pyvisa-py

Run:
    python lakeshore335_pyqt_control.py

Typical VISA addresses:
    USB virtual COM on Windows: ASRL3::INSTR, ASRL4::INSTR, ...
    GPIB: GPIB0::12::INSTR or GPIB::12::INSTR
"""

import sys
import csv
import os
import threading
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

import pyvisa
from pyvisa.constants import Parity, StopBits
from PyQt5.QtCore import Qt, QObject, QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class LakeShore335:
    """Small PyVISA driver for common Lake Shore 335 operations."""

    def __init__(self, visa_address: str, resource_manager: Optional[pyvisa.ResourceManager] = None):
        if not visa_address:
            raise ValueError("visa_address must not be empty")

        self.visa_address = visa_address
        self.resource_manager = resource_manager or pyvisa.ResourceManager()
        self.device = self.resource_manager.open_resource(visa_address)

        # The 335 USB interface appears as a virtual serial port.
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

    def write(self, command: str) -> None:
        self.device.write(command)

    def query(self, command: str) -> str:
        return self.device.query(command).strip()

    def get_temperature(self, channel: str = "A") -> float:
        # return float(self.query(f"KRDG? {channel}"))
        
    # def get_temperature(self, channel='A'):
        """
        Get the current temperature reading from a specific channel.

        :param channel: Channel to read the temperature from ('A' or 'B').
        :return: Current temperature in Kelvin.
        """
        response = self.device.query(f"KRDG? {channel}\r")
        
        try:
            temp = float(response)
            
        except:
            
            time.sleep(5)
            
            response = self.device.query(f"KRDG? {channel}\r")
            
            temp = float(response)
            
        return temp    
    

    def set_temperature(self, setpoint: float, loop: int = 1) -> None:
        self.write(f"SETP {loop},{setpoint}")

    def get_setpoint(self, loop: int = 1) -> float:
        return float(self.query(f"SETP? {loop}"))

    def set_heater_range(self, output: int, range_level: int) -> None:
        # 0 = off, 1 = low, 2 = medium, 3 = high
        self.write(f"RANGE {output},{range_level}")

    def get_heater_range(self, output: int = 1) -> int:
        return int(float(self.query(f"RANGE? {output}")))

    def get_heater_percent(self, output: int = 1) -> float:
        return float(self.query(f"HTR? {output}"))

    def set_pid(self, p: float, i: float, d: float, loop: int = 1) -> None:
        self.write(f"PID {loop},{p},{i},{d}")

    def get_pid(self, loop: int = 1) -> Tuple[float, float, float]:
        values = self.query(f"PID? {loop}").split(",")
        if len(values) != 3:
            raise RuntimeError(f"Unexpected PID response: {values!r}")
        return tuple(map(float, values))  # type: ignore[return-value]

    def all_heaters_off(self) -> None:
        # The safest generic approach: explicitly set both output ranges to off.
        self.set_heater_range(1, 0)
        self.set_heater_range(2, 0)

    def close(self) -> None:
        try:
            self.device.close()
        finally:
            pass


@dataclass
class Reading:
    temperature_a: Optional[float] = None
    temperature_b: Optional[float] = None
    heater_1: Optional[float] = None
    heater_2: Optional[float] = None
    setpoint_1: Optional[float] = None
    setpoint_2: Optional[float] = None
    range_1: Optional[int] = None
    range_2: Optional[int] = None


@dataclass
class AutoTuneConfig:
    loop: int
    input_channel: str
    target: float
    heater_range: int
    tolerance: float
    max_iterations: int
    window_seconds: int
    sample_interval: float


@dataclass
class AutoTuneMetrics:
    mean_abs_error: float
    final_error: float
    overshoot: float
    oscillations: int
    heater_saturated: bool


class DeviceWorker(QObject):
    connected = pyqtSignal(str)
    disconnected = pyqtSignal()
    reading = pyqtSignal(object)
    error = pyqtSignal(str)
    log = pyqtSignal(str)
    autotune_started = pyqtSignal()
    autotune_finished = pyqtSignal(int, float, float, float)
    autotune_stopped = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.controller: Optional[LakeShore335] = None
        self._autotune_cancel = threading.Event()

    @pyqtSlot(str)
    def connect_device(self, visa_address: str) -> None:
        try:
            self.controller = LakeShore335(visa_address=visa_address)
            self.connected.emit(self.controller.identity)
            self.log.emit(f"Connected: {self.controller.identity}")
        except Exception as exc:
            self.controller = None
            self.error.emit(f"Connection failed: {exc}")

    @pyqtSlot()
    def disconnect_device(self) -> None:
        if self.controller is not None:
            try:
                self.controller.close()
            except Exception as exc:
                self.error.emit(f"Disconnect error: {exc}")
        self.controller = None
        self.disconnected.emit()
        self.log.emit("Disconnected")

    @pyqtSlot()
    def poll(self) -> None:
        if self.controller is None:
            return
        try:
            r = Reading(
                temperature_a=self.controller.get_temperature("A"),
                temperature_b=self.controller.get_temperature("B"),
                heater_1=self.controller.get_heater_percent(1),
                heater_2=self.controller.get_heater_percent(2),
                setpoint_1=self.controller.get_setpoint(1),
                setpoint_2=self.controller.get_setpoint(2),
                range_1=self.controller.get_heater_range(1),
                range_2=self.controller.get_heater_range(2),
            )
            self.reading.emit(r)
        except Exception as exc:
            self.error.emit(f"Poll failed: {exc}")

    @pyqtSlot(int, float)
    def set_setpoint(self, loop: int, setpoint: float) -> None:
        if self.controller is None:
            self.error.emit("Not connected")
            return
        try:
            self.controller.set_temperature(setpoint, loop)
            self.log.emit(f"Set loop {loop} setpoint to {setpoint:.4f} K")
        except Exception as exc:
            self.error.emit(f"Setpoint write failed: {exc}")

    @pyqtSlot(int, int)
    def set_heater_range(self, output: int, range_level: int) -> None:
        if self.controller is None:
            self.error.emit("Not connected")
            return
        try:
            self.controller.set_heater_range(output, range_level)
            self.log.emit(f"Set output {output} heater range to {range_level}")
        except Exception as exc:
            self.error.emit(f"Heater range write failed: {exc}")

    @pyqtSlot(int, float, float, float)
    def set_pid(self, loop: int, p: float, i: float, d: float) -> None:
        if self.controller is None:
            self.error.emit("Not connected")
            return
        try:
            self.controller.set_pid(p, i, d, loop)
            self.log.emit(f"Set loop {loop} PID to P={p:g}, I={i:g}, D={d:g}")
        except Exception as exc:
            self.error.emit(f"PID write failed: {exc}")

    @pyqtSlot()
    def read_pid(self) -> None:
        if self.controller is None:
            self.error.emit("Not connected")
            return
        try:
            p1, i1, d1 = self.controller.get_pid(1)
            p2, i2, d2 = self.controller.get_pid(2)
            self.log.emit(f"Loop 1 PID: P={p1:g}, I={i1:g}, D={d1:g}")
            self.log.emit(f"Loop 2 PID: P={p2:g}, I={i2:g}, D={d2:g}")
        except Exception as exc:
            self.error.emit(f"PID read failed: {exc}")

    @pyqtSlot()
    def all_heaters_off(self) -> None:
        if self.controller is None:
            self.error.emit("Not connected")
            return
        try:
            self.controller.all_heaters_off()
            self.log.emit("Both heater ranges set to OFF")
        except Exception as exc:
            self.error.emit(f"All-off failed: {exc}")

    def cancel_autotune(self) -> None:
        self._autotune_cancel.set()
        self.log.emit("Auto tune stop requested")

    @pyqtSlot(int, str, float, int, float, int, int, float)
    def auto_tune_pid(
        self,
        loop: int,
        input_channel: str,
        target: float,
        heater_range: int,
        tolerance: float,
        max_iterations: int,
        window_seconds: int,
        sample_interval: float,
    ) -> None:
        if self.controller is None:
            self.error.emit("Not connected")
            return

        cfg = AutoTuneConfig(
            loop=loop,
            input_channel=input_channel,
            target=target,
            heater_range=heater_range,
            tolerance=max(tolerance, 0.001),
            max_iterations=max(max_iterations, 1),
            window_seconds=max(window_seconds, 30),
            sample_interval=max(sample_interval, 0.5),
        )

        self._autotune_cancel.clear()
        self.autotune_started.emit()
        
        print('function run here')
        
        if True:
            p, i, d = self.controller.get_pid(cfg.loop)
            if p <= 0 and i <= 0 and d <= 0:
                p, i, d = 10.0, 20.0, 0.0

            self.controller.set_temperature(cfg.target, cfg.loop)
            self.controller.set_heater_range(cfg.loop, cfg.heater_range)
            self.log.emit(
                "Auto tune started: "
                f"loop={cfg.loop}, input={cfg.input_channel}, target={cfg.target:.4f} K, "
                f"range={cfg.heater_range}, tolerance={cfg.tolerance:.4f} K"
            )

            best_pid = (p, i, d)
            best_score = float("inf")
            for iteration in range(1, cfg.max_iterations + 1):
                if self._autotune_cancel.is_set():
                    self.log.emit("Auto tune cancelled before next trial")
                    break

                self.controller.set_pid(p, i, d, cfg.loop)
                self.log.emit(
                    f"Trial {iteration}/{cfg.max_iterations}: "
                    f"P={p:g}, I={i:g}, D={d:g}"
                )

                samples = self._collect_autotune_samples(cfg)
                if not samples:
                    self.log.emit("Auto tune stopped with no samples collected")
                    break

                metrics = self._evaluate_autotune_samples(samples, cfg.target, cfg.tolerance)
                score = (
                    metrics.mean_abs_error
                    + 2.0 * metrics.overshoot
                    + 0.25 * metrics.oscillations
                    + (2.0 if metrics.heater_saturated else 0.0)
                )
                self.log.emit(
                    f"Trial {iteration} result: mean error={metrics.mean_abs_error:.4f} K, "
                    f"final error={metrics.final_error:.4f} K, overshoot={metrics.overshoot:.4f} K, "
                    f"oscillations={metrics.oscillations}, saturated={metrics.heater_saturated}"
                )

                if score < best_score:
                    best_score = score
                    best_pid = (p, i, d)

                if (
                    metrics.mean_abs_error <= cfg.tolerance
                    and abs(metrics.final_error) <= cfg.tolerance
                    and metrics.overshoot <= cfg.tolerance
                    and metrics.oscillations <= 1
                ):
                    self.log.emit("Auto tune converged inside tolerance")
                    break

                p, i, d = self._next_pid_trial(p, i, d, metrics, cfg.tolerance)

            final_p, final_i, final_d = best_pid
            self.controller.set_pid(final_p, final_i, final_d, cfg.loop)
            self.log.emit(
                f"Auto tune finished. Best loop {cfg.loop} PID: "
                f"P={final_p:g}, I={final_i:g}, D={final_d:g}"
            )
            self.autotune_finished.emit(cfg.loop, final_p, final_i, final_d)
        #except Exception as exc:
        #    self.error.emit(f"Auto tune failed: {exc}")
        #finally:
        #    self._autotune_cancel.clear()
        #    self.autotune_stopped.emit()

    def _collect_autotune_samples(self, cfg: AutoTuneConfig) -> List[Tuple[float, float, float]]:
        samples: List[Tuple[float, float, float]] = []
        started = time.monotonic()
        while time.monotonic() - started < cfg.window_seconds:
            if self._autotune_cancel.is_set():
                return samples
            temperature = self.controller.get_temperature(cfg.input_channel)  # type: ignore[union-attr]
            heater = self.controller.get_heater_percent(cfg.loop)  # type: ignore[union-attr]
            elapsed = time.monotonic() - started
            samples.append((elapsed, temperature, heater))
            self.log.emit(
                f"Auto tune sample: t={elapsed:.0f}s, T={temperature:.4f} K, heater={heater:.1f}%"
            )
            self.reading.emit(self._read_current_values())
            self._sleep_autotune_interval(cfg.sample_interval)
        return samples

    def _sleep_autotune_interval(self, seconds: float) -> None:
        end_time = time.monotonic() + seconds
        while time.monotonic() < end_time:
            if self._autotune_cancel.is_set():
                return
            time.sleep(min(0.2, end_time - time.monotonic()))

    def _read_current_values(self) -> Reading:
        return Reading(
            temperature_a=self.controller.get_temperature("A"),  # type: ignore[union-attr]
            temperature_b=self.controller.get_temperature("B"),  # type: ignore[union-attr]
            heater_1=self.controller.get_heater_percent(1),  # type: ignore[union-attr]
            heater_2=self.controller.get_heater_percent(2),  # type: ignore[union-attr]
            setpoint_1=self.controller.get_setpoint(1),  # type: ignore[union-attr]
            setpoint_2=self.controller.get_setpoint(2),  # type: ignore[union-attr]
            range_1=self.controller.get_heater_range(1),  # type: ignore[union-attr]
            range_2=self.controller.get_heater_range(2),  # type: ignore[union-attr]
        )

    @staticmethod
    def _evaluate_autotune_samples(
        samples: List[Tuple[float, float, float]],
        target: float,
        tolerance: float,
    ) -> AutoTuneMetrics:
        temperatures = [temperature for _, temperature, _ in samples]
        heaters = [heater for _, _, heater in samples]
        errors = [target - temperature for temperature in temperatures]
        mean_abs_error = sum(abs(error) for error in errors) / len(errors)
        final_error = errors[-1]
        overshoot = max(0.0, max(temperature - target for temperature in temperatures))
        signs = [1 if error > tolerance else -1 if error < -tolerance else 0 for error in errors]
        nonzero_signs = [sign for sign in signs if sign != 0]
        oscillations = sum(
            1 for previous, current in zip(nonzero_signs, nonzero_signs[1:]) if previous != current
        )
        heater_saturated = any(heater >= 98.0 for heater in heaters)
        return AutoTuneMetrics(mean_abs_error, final_error, overshoot, oscillations, heater_saturated)

    @staticmethod
    def _next_pid_trial(
        p: float,
        i: float,
        d: float,
        metrics: AutoTuneMetrics,
        tolerance: float,
    ) -> Tuple[float, float, float]:
        if metrics.oscillations >= 2 or metrics.overshoot > 3.0 * tolerance:
            p *= 0.75
            i *= 0.80
            d = max(d * 1.20, p * 0.05)
        elif metrics.heater_saturated:
            p *= 0.85
            i *= 0.90
            d *= 1.05
        elif abs(metrics.final_error) > 2.0 * tolerance:
            p *= 1.20
            i *= 1.15
        else:
            p *= 1.08
            i *= 1.05
            d *= 1.05

        return (
            min(max(p, 0.0), 10000.0),
            min(max(i, 0.0), 10000.0),
            min(max(d, 0.0), 10000.0),
        )


class TemperaturePlotWidget(QWidget):
    """Lightweight real-time plot for Lake Shore input A and B temperatures."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumHeight(220)
        self.max_points = 3600
        self.samples: List[Tuple[float, Optional[float], Optional[float]]] = []

    def add_reading(self, temperature_a: Optional[float], temperature_b: Optional[float]) -> None:
        if temperature_a is None and temperature_b is None:
            return
        self.samples.append((time.time(), temperature_a, temperature_b))
        if len(self.samples) > self.max_points:
            self.samples = self.samples[-self.max_points:]
        self.update()

    def clear(self) -> None:
        self.samples.clear()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(255, 255, 255))

        left, right, top, bottom = 58, 18, 18, 34
        width = max(1, self.width() - left - right)
        height = max(1, self.height() - top - bottom)
        x0, y0 = left, top + height

        painter.setPen(QPen(QColor(70, 70, 70), 1))
        painter.drawRect(left, top, width, height)

        values = [
            value
            for _, temperature_a, temperature_b in self.samples
            for value in (temperature_a, temperature_b)
            if value is not None
        ]
        if not values:
            painter.setPen(QColor(100, 100, 100))
            painter.drawText(self.rect(), Qt.AlignCenter, "Waiting for temperature data")
            return

        min_temp = min(values)
        max_temp = max(values)
        if abs(max_temp - min_temp) < 1e-9:
            min_temp -= 0.5
            max_temp += 0.5
        else:
            pad = (max_temp - min_temp) * 0.10
            min_temp -= pad
            max_temp += pad

        first_time = self.samples[0][0]
        last_time = self.samples[-1][0]
        time_span = max(1.0, last_time - first_time)

        def point(sample_time: float, temperature: float) -> Tuple[int, int]:
            x = x0 + int((sample_time - first_time) / time_span * width)
            y = top + int((max_temp - temperature) / (max_temp - min_temp) * height)
            return x, y

        painter.setPen(QPen(QColor(225, 225, 225), 1))
        for grid_index in range(1, 5):
            y = top + int(height * grid_index / 5)
            painter.drawLine(left, y, left + width, y)

        painter.setPen(QColor(60, 60, 60))
        painter.drawText(4, top + 10, f"{max_temp:.3f} K")
        painter.drawText(4, y0, f"{min_temp:.3f} K")
        painter.drawText(left, self.height() - 10, time.strftime("%H:%M:%S", time.localtime(first_time)))
        painter.drawText(left + width - 62, self.height() - 10, time.strftime("%H:%M:%S", time.localtime(last_time)))

        self._draw_temperature_line(painter, 1, QColor(25, 115, 232), point)
        self._draw_temperature_line(painter, 2, QColor(217, 48, 37), point)

        painter.setPen(QPen(QColor(25, 115, 232), 3))
        painter.drawLine(left + 8, top + 10, left + 32, top + 10)
        painter.setPen(QColor(40, 40, 40))
        painter.drawText(left + 38, top + 15, "Temp 1 / Input A")
        painter.setPen(QPen(QColor(217, 48, 37), 3))
        painter.drawLine(left + 160, top + 10, left + 184, top + 10)
        painter.setPen(QColor(40, 40, 40))
        painter.drawText(left + 190, top + 15, "Temp 2 / Input B")

    def _draw_temperature_line(self, painter: QPainter, channel_index: int, color: QColor, point_func) -> None:
        painter.setPen(QPen(color, 2))
        previous: Optional[Tuple[int, int]] = None
        for sample_time, temperature_a, temperature_b in self.samples:
            temperature = temperature_a if channel_index == 1 else temperature_b
            if temperature is None:
                previous = None
                continue
            current = point_func(sample_time, temperature)
            if previous is not None:
                painter.drawLine(previous[0], previous[1], current[0], current[1])
            previous = current


class MainWindow(QMainWindow):
    request_connect = pyqtSignal(str)
    request_disconnect = pyqtSignal()
    request_poll = pyqtSignal()
    request_setpoint = pyqtSignal(int, float)
    request_heater_range = pyqtSignal(int, int)
    request_pid = pyqtSignal(int, float, float, float)
    request_read_pid = pyqtSignal()
    request_all_off = pyqtSignal()
    request_autotune = pyqtSignal(int, str, float, int, float, int, int, float)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Lake Shore 335 Control")
        self.resize(860, 620)

        self.worker_thread = QThread(self)
        self.worker = DeviceWorker()
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.start()
        self.temperature_log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temperature_log.csv")
        self._temperature_log_ready = False

        self._build_ui()
        self._wire_signals()
        

        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(1000)
        self.poll_timer.timeout.connect(self.request_poll)
        
        self._set_connected_state(False)

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        conn_box = QGroupBox("Connection")
        conn_layout = QHBoxLayout(conn_box)
        self.address_edit = QLineEdit("ASRL3::INSTR")
        self.address_edit.setPlaceholderText("ASRL3::INSTR or GPIB0::12::INSTR")
        self.connect_btn = QPushButton("Connect")
        self.disconnect_btn = QPushButton("Disconnect")
        self.status_label = QLabel("Not connected")
        conn_layout.addWidget(QLabel("VISA address:"))
        conn_layout.addWidget(self.address_edit, 1)
        conn_layout.addWidget(self.connect_btn)
        conn_layout.addWidget(self.disconnect_btn)
        conn_layout.addWidget(self.status_label, 2)
        layout.addWidget(conn_box)

        read_box = QGroupBox("Live readings")
        read_layout = QGridLayout(read_box)
        self.temp_a_label = QLabel("-- K")
        self.temp_b_label = QLabel("-- K")
        self.htr1_label = QLabel("-- %")
        self.htr2_label = QLabel("-- %")
        self.sp1_label = QLabel("-- K")
        self.sp2_label = QLabel("-- K")
        self.range1_label = QLabel("--")
        self.range2_label = QLabel("--")
        labels = [
            ("Input A", self.temp_a_label), ("Input B", self.temp_b_label),
            ("Heater 1", self.htr1_label), ("Heater 2", self.htr2_label),
            ("Setpoint 1", self.sp1_label), ("Setpoint 2", self.sp2_label),
            ("Range 1", self.range1_label), ("Range 2", self.range2_label),
        ]
        for row, (name, widget) in enumerate(labels):
            read_layout.addWidget(QLabel(name + ":"), row // 2, (row % 2) * 2)
            read_layout.addWidget(widget, row // 2, (row % 2) * 2 + 1)
        layout.addWidget(read_box)

        plot_box = QGroupBox("Temperature curve and log")
        plot_layout = QVBoxLayout(plot_box)
        self.temperature_plot = TemperaturePlotWidget()
        self.temperature_log_label = QLabel(f"Log file: {self.temperature_log_path}")
        plot_layout.addWidget(self.temperature_plot)
        plot_layout.addWidget(self.temperature_log_label)
        layout.addWidget(plot_box)

        control_row = QHBoxLayout()
        control_row.addWidget(self._make_setpoint_box(1))
        control_row.addWidget(self._make_setpoint_box(2))
        control_row.addWidget(self._make_heater_box())
        layout.addLayout(control_row)

        pid_row = QHBoxLayout()
        pid_row.addWidget(self._make_pid_box(1))
        pid_row.addWidget(self._make_pid_box(2))
        layout.addLayout(pid_row)

        layout.addWidget(self._make_autotune_box())

        self.all_off_btn = QPushButton("EMERGENCY: all heaters OFF")
        layout.addWidget(self.all_off_btn)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text, 1)

    def _make_setpoint_box(self, loop: int) -> QGroupBox:
        box = QGroupBox(f"Loop {loop} setpoint")
        form = QFormLayout(box)
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 2000.0)
        spin.setDecimals(4)
        spin.setSuffix(" K")
        spin.setSingleStep(0.1)
        btn = QPushButton(f"Apply loop {loop}")
        setattr(self, f"setpoint_spin_{loop}", spin)
        setattr(self, f"setpoint_btn_{loop}", btn)
        form.addRow("Target:", spin)
        form.addRow(btn)
        return box

    def _make_heater_box(self) -> QGroupBox:
        box = QGroupBox("Heater range")
        form = QFormLayout(box)
        self.output_combo = QComboBox()
        self.output_combo.addItems(["1", "2"])
        self.range_combo = QComboBox()
        self.range_combo.addItems(["0 - Off", "1 - Low", "2 - Medium", "3 - High"])
        self.range_btn = QPushButton("Apply range")
        form.addRow("Output:", self.output_combo)
        form.addRow("Range:", self.range_combo)
        form.addRow(self.range_btn)
        return box

    def _make_pid_box(self, loop: int) -> QGroupBox:
        box = QGroupBox(f"Loop {loop} PID")
        form = QFormLayout(box)
        p = QDoubleSpinBox(); p.setRange(0, 10000); p.setDecimals(4); p.setValue(10.0)
        i = QDoubleSpinBox(); i.setRange(0, 10000); i.setDecimals(4); i.setValue(20.0)
        d = QDoubleSpinBox(); d.setRange(0, 10000); d.setDecimals(4); d.setValue(0.0)
        btn = QPushButton(f"Apply PID loop {loop}")
        read_btn = QPushButton("Read both PID")
        setattr(self, f"pid_p_{loop}", p)
        setattr(self, f"pid_i_{loop}", i)
        setattr(self, f"pid_d_{loop}", d)
        setattr(self, f"pid_btn_{loop}", btn)
        if loop == 1:
            self.read_pid_btn = read_btn
        form.addRow("P:", p)
        form.addRow("I:", i)
        form.addRow("D:", d)
        form.addRow(btn)
        if loop == 1:
            form.addRow(read_btn)
        return box

    def _make_autotune_box(self) -> QGroupBox:
        box = QGroupBox("Automatic PID tuning")
        layout = QGridLayout(box)

        self.autotune_loop_combo = QComboBox()
        self.autotune_loop_combo.addItems(["1", "2"])
        self.autotune_input_combo = QComboBox()
        self.autotune_input_combo.addItems(["A", "B"])

        self.autotune_target_spin = QDoubleSpinBox()
        self.autotune_target_spin.setRange(0.0, 2000.0)
        self.autotune_target_spin.setDecimals(4)
        self.autotune_target_spin.setSuffix(" K")
        self.autotune_target_spin.setSingleStep(0.1)

        self.autotune_range_combo = QComboBox()
        self.autotune_range_combo.addItems(["1 - Low", "2 - Medium", "3 - High"])

        self.autotune_tolerance_spin = QDoubleSpinBox()
        self.autotune_tolerance_spin.setRange(0.001, 100.0)
        self.autotune_tolerance_spin.setDecimals(4)
        self.autotune_tolerance_spin.setSuffix(" K")
        self.autotune_tolerance_spin.setValue(0.05)

        self.autotune_iterations_spin = QSpinBox()
        self.autotune_iterations_spin.setRange(1, 20)
        self.autotune_iterations_spin.setValue(5)

        self.autotune_window_spin = QSpinBox()
        self.autotune_window_spin.setRange(30, 7200)
        self.autotune_window_spin.setSuffix(" s")
        self.autotune_window_spin.setValue(180)

        self.autotune_sample_spin = QDoubleSpinBox()
        self.autotune_sample_spin.setRange(0.5, 120.0)
        self.autotune_sample_spin.setDecimals(1)
        self.autotune_sample_spin.setSuffix(" s")
        self.autotune_sample_spin.setValue(5.0)

        self.autotune_start_btn = QPushButton("Start auto tune")
        self.autotune_stop_btn = QPushButton("Stop auto tune")

        layout.addWidget(QLabel("Loop:"), 0, 0)
        layout.addWidget(self.autotune_loop_combo, 0, 1)
        layout.addWidget(QLabel("Input:"), 0, 2)
        layout.addWidget(self.autotune_input_combo, 0, 3)
        layout.addWidget(QLabel("Target:"), 0, 4)
        layout.addWidget(self.autotune_target_spin, 0, 5)

        layout.addWidget(QLabel("Range:"), 1, 0)
        layout.addWidget(self.autotune_range_combo, 1, 1)
        layout.addWidget(QLabel("Tolerance:"), 1, 2)
        layout.addWidget(self.autotune_tolerance_spin, 1, 3)
        layout.addWidget(QLabel("Trials:"), 1, 4)
        layout.addWidget(self.autotune_iterations_spin, 1, 5)

        layout.addWidget(QLabel("Trial time:"), 2, 0)
        layout.addWidget(self.autotune_window_spin, 2, 1)
        layout.addWidget(QLabel("Sample every:"), 2, 2)
        layout.addWidget(self.autotune_sample_spin, 2, 3)
        layout.addWidget(self.autotune_start_btn, 2, 4)
        layout.addWidget(self.autotune_stop_btn, 2, 5)
        return box

    def _wire_signals(self) -> None:
        self.connect_btn.clicked.connect(lambda: self.request_connect.emit(self.address_edit.text().strip()))
        self.disconnect_btn.clicked.connect(self.request_disconnect)
        self.request_connect.connect(self.worker.connect_device)
        self.request_disconnect.connect(self.worker.disconnect_device)
        self.request_poll.connect(self.worker.poll)
        self.request_setpoint.connect(self.worker.set_setpoint)
        self.request_heater_range.connect(self.worker.set_heater_range)
        self.request_pid.connect(self.worker.set_pid)
        self.request_read_pid.connect(self.worker.read_pid)
        self.request_all_off.connect(self.worker.all_heaters_off)
        self.request_autotune.connect(self.worker.auto_tune_pid)

        self.worker.connected.connect(self._on_connected)
        self.worker.disconnected.connect(lambda: self._set_connected_state(False))
        self.worker.reading.connect(self._update_reading)
        self.worker.error.connect(self._show_error)
        self.worker.log.connect(self._log)
        self.worker.autotune_started.connect(self._on_autotune_started)
        self.worker.autotune_finished.connect(self._on_autotune_finished)
        self.worker.autotune_stopped.connect(self._on_autotune_stopped)

        self.setpoint_btn_1.clicked.connect(lambda: self.request_setpoint.emit(1, self.setpoint_spin_1.value()))
        self.setpoint_btn_2.clicked.connect(lambda: self.request_setpoint.emit(2, self.setpoint_spin_2.value()))
        self.range_btn.clicked.connect(self._apply_range)
        self.pid_btn_1.clicked.connect(lambda: self._apply_pid(1))
        self.pid_btn_2.clicked.connect(lambda: self._apply_pid(2))
        self.read_pid_btn.clicked.connect(self.request_read_pid)
        self.autotune_start_btn.clicked.connect(self._start_autotune)
        self.autotune_stop_btn.clicked.connect(self.worker.cancel_autotune)
        self.all_off_btn.clicked.connect(self._confirm_all_off)

    def _set_connected_state(self, connected: bool) -> None:
        self.connect_btn.setEnabled(not connected)
        self.disconnect_btn.setEnabled(connected)
        for widget in [
            self.setpoint_btn_1, self.setpoint_btn_2, self.range_btn,
            self.pid_btn_1, self.pid_btn_2, self.read_pid_btn, self.all_off_btn,
            self.autotune_start_btn, self.autotune_stop_btn,
        ]:
            widget.setEnabled(connected)
        if connected:
            self.autotune_stop_btn.setEnabled(False)
        self.status_label.setText("Connected" if connected else "Not connected")
        if connected:
            self.poll_timer.start()
        else:
            self.poll_timer.stop()
            if hasattr(self, "temperature_plot"):
                self.temperature_plot.clear()

    def _on_connected(self, identity: str) -> None:
        self.status_label.setText(identity)
        self._ensure_temperature_log()
        self._log(f"Temperature log: {self.temperature_log_path}")
        self._set_connected_state(True)
        self.request_poll.emit()

    def _apply_range(self) -> None:
        output = int(self.output_combo.currentText())
        range_level = self.range_combo.currentIndex()
        self.request_heater_range.emit(output, range_level)

    def _apply_pid(self, loop: int) -> None:
        p = getattr(self, f"pid_p_{loop}").value()
        i = getattr(self, f"pid_i_{loop}").value()
        d = getattr(self, f"pid_d_{loop}").value()
        self.request_pid.emit(loop, p, i, d)

    def _start_autotune(self) -> None:
        loop = int(self.autotune_loop_combo.currentText())
        input_channel = self.autotune_input_combo.currentText()
        target = self.autotune_target_spin.value()
        heater_range = self.autotune_range_combo.currentIndex() + 1
        tolerance = self.autotune_tolerance_spin.value()
        max_iterations = self.autotune_iterations_spin.value()
        window_seconds = self.autotune_window_spin.value()
        sample_interval = self.autotune_sample_spin.value()
        self.request_autotune.emit(
            loop,
            input_channel,
            target,
            heater_range,
            tolerance,
            max_iterations,
            window_seconds,
            sample_interval,
        )

    def _on_autotune_started(self) -> None:
        self.poll_timer.stop()
        self.autotune_start_btn.setEnabled(False)
        self.autotune_stop_btn.setEnabled(True)

    def _on_autotune_finished(self, loop: int, p: float, i: float, d: float) -> None:
        getattr(self, f"pid_p_{loop}").setValue(p)
        getattr(self, f"pid_i_{loop}").setValue(i)
        getattr(self, f"pid_d_{loop}").setValue(d)

    def _on_autotune_stopped(self) -> None:
        self.autotune_start_btn.setEnabled(True)
        self.autotune_stop_btn.setEnabled(False)
        if self.controller_is_connected():
            self.poll_timer.start()

    def controller_is_connected(self) -> bool:
        return self.disconnect_btn.isEnabled()

    def _confirm_all_off(self) -> None:
        reply = QMessageBox.warning(
            self,
            "Confirm heater off",
            "Set both heater output ranges to OFF?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.worker.cancel_autotune()
            self.request_all_off.emit()

    def _update_reading(self, r: Reading) -> None:
        self.temp_a_label.setText(self._fmt(r.temperature_a, "K", 4))
        self.temp_b_label.setText(self._fmt(r.temperature_b, "K", 4))
        self.htr1_label.setText(self._fmt(r.heater_1, "%", 2))
        self.htr2_label.setText(self._fmt(r.heater_2, "%", 2))
        self.sp1_label.setText(self._fmt(r.setpoint_1, "K", 4))
        self.sp2_label.setText(self._fmt(r.setpoint_2, "K", 4))
        self.range1_label.setText(str(r.range_1) if r.range_1 is not None else "--")
        self.range2_label.setText(str(r.range_2) if r.range_2 is not None else "--")
        self.temperature_plot.add_reading(r.temperature_a, r.temperature_b)
        self._append_temperature_log(r.temperature_a, r.temperature_b)

    def _ensure_temperature_log(self) -> None:
        if self._temperature_log_ready:
            return
        file_exists = os.path.exists(self.temperature_log_path)
        with open(self.temperature_log_path, "a", newline="", encoding="utf-8-sig") as csv_file:
            writer = csv.writer(csv_file)
            if not file_exists or os.path.getsize(self.temperature_log_path) == 0:
                writer.writerow(["时间", "温度1", "温度2"])
        self._temperature_log_ready = True

    def _append_temperature_log(
        self,
        temperature_a: Optional[float],
        temperature_b: Optional[float],
    ) -> None:
        if temperature_a is None and temperature_b is None:
            return
        self._ensure_temperature_log()
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(self.temperature_log_path, "a", newline="", encoding="utf-8-sig") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow([
                timestamp,
                "" if temperature_a is None else f"{temperature_a:.6f}",
                "" if temperature_b is None else f"{temperature_b:.6f}",
            ])

    @staticmethod
    def _fmt(value: Optional[float], unit: str, decimals: int) -> str:
        if value is None:
            return f"-- {unit}"
        return f"{value:.{decimals}f} {unit}"

    def _show_error(self, message: str) -> None:
        self._log("ERROR: " + message)
        QMessageBox.critical(self, "Lake Shore 335 error", message)

    def _log(self, message: str) -> None:
        self.log_text.append(time.strftime("[%H:%M:%S] ") + message)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self.poll_timer.stop()
        self.request_disconnect.emit()
        self.worker_thread.quit()
        self.worker_thread.wait(2000)
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
