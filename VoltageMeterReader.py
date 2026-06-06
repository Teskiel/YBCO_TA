# -*- coding: utf-8 -*-
"""
Created on Tue Jun  2 00:02:03 2026

@author: DELL
"""

import sys
import time
import pyvisa

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QPushButton,
    QDoubleSpinBox,
    QLineEdit,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QVBoxLayout,
    QMessageBox,
    QGroupBox,
)


class KeysightE36312A:
    def __init__(self, resource_name):
        self.rm = pyvisa.ResourceManager()
        self.inst = self.rm.open_resource(resource_name)

        self.inst.timeout = 5000
        self.inst.write_termination = "\n"
        self.inst.read_termination = "\n"

    def write(self, cmd):
        self.inst.write(cmd)

    def query(self, cmd):
        return self.inst.query(cmd).strip()

    def idn(self):
        return self.query("*IDN?")

    def clear(self):
        self.write("*CLS")

    def reset(self):
        self.write("*RST")
        time.sleep(1)

    def select_channel(self, ch):
        self.write(f"INST:NSEL {ch}")

    def set_voltage(self, ch, voltage):
        self.select_channel(ch)
        self.write(f"VOLT {voltage}")

    def set_current(self, ch, current):
        self.select_channel(ch)
        self.write(f"CURR {current}")

    def set_channel(self, ch, voltage, current):
        self.select_channel(ch)
        self.write(f"VOLT {voltage}")
        self.write(f"CURR {current}")

    def output_on(self, ch):
        self.select_channel(ch)
        self.write("OUTP ON")

    def output_off(self, ch):
        self.select_channel(ch)
        self.write("OUTP OFF")

    def measure_voltage(self, ch):
        self.select_channel(ch)
        return float(self.query("MEAS:VOLT?"))

    def measure_current(self, ch):
        self.select_channel(ch)
        return float(self.query("MEAS:CURR?"))

    def get_error(self):
        return self.query("SYST:ERR?")

    def close(self):
        try:
            self.inst.close()
        finally:
            self.rm.close()


class ChannelControl(QGroupBox):
    def __init__(self, channel_number, voltage_max, current_max):
        super().__init__(f"Channel {channel_number}")

        self.channel = channel_number

        self.voltage_spin = QDoubleSpinBox()
        self.voltage_spin.setRange(0.0, voltage_max)
        self.voltage_spin.setDecimals(3)
        self.voltage_spin.setSingleStep(0.1)
        self.voltage_spin.setSuffix(" V")

        self.current_spin = QDoubleSpinBox()
        self.current_spin.setRange(0.0, current_max)
        self.current_spin.setDecimals(3)
        self.current_spin.setSingleStep(0.01)
        self.current_spin.setSuffix(" A")

        self.apply_button = QPushButton("Apply V/I")
        self.on_button = QPushButton("Output ON")
        self.off_button = QPushButton("Output OFF")
        self.measure_button = QPushButton("Measure")

        self.measured_voltage_label = QLabel("Measured V: ---")
        self.measured_current_label = QLabel("Measured I: ---")
        self.status_label = QLabel("Status: ---")

        layout = QGridLayout()
        layout.addWidget(QLabel("Voltage setpoint:"), 0, 0)
        layout.addWidget(self.voltage_spin, 0, 1)

        layout.addWidget(QLabel("Current limit:"), 1, 0)
        layout.addWidget(self.current_spin, 1, 1)

        layout.addWidget(self.apply_button, 2, 0, 1, 2)
        layout.addWidget(self.on_button, 3, 0)
        layout.addWidget(self.off_button, 3, 1)
        layout.addWidget(self.measure_button, 4, 0, 1, 2)

        layout.addWidget(self.measured_voltage_label, 5, 0, 1, 2)
        layout.addWidget(self.measured_current_label, 6, 0, 1, 2)
        layout.addWidget(self.status_label, 7, 0, 1, 2)

        self.setLayout(layout)


class PowerSupplyGUI(QWidget):
    def __init__(self):
        super().__init__()

        self.psu = None

        self.setWindowTitle("Keysight E36312A Triple Output Control")

        self.resource_input = QLineEdit()
        self.resource_input.setPlaceholderText(
            "Example: USB0::0x2A8D::0x1102::MY61008456::INSTR"
        )

        self.resource_combo = QComboBox()
        self.refresh_button = QPushButton("Refresh VISA")
        self.connect_button = QPushButton("Connect")
        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.setEnabled(False)

        self.idn_label = QLabel("Instrument: Not connected")

        self.reset_button = QPushButton("Reset")
        self.clear_button = QPushButton("Clear Errors")
        self.error_button = QPushButton("Read Error")
        self.error_label = QLabel("Error: ---")

        self.reset_button.setEnabled(False)
        self.clear_button.setEnabled(False)
        self.error_button.setEnabled(False)

        # E36312A typical ratings:
        # CH1: 6 V / 5 A
        # CH2: 25 V / 1 A
        # CH3: 25 V / 1 A
        self.channels = [
            ChannelControl(1, voltage_max=6.0, current_max=5.0),
            ChannelControl(2, voltage_max=25.0, current_max=1.0),
            ChannelControl(3, voltage_max=25.0, current_max=1.0),
        ]

        self.auto_measure_button = QPushButton("Start Auto Measure")
        self.auto_measure_enabled = False

        self.timer = QTimer()
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.measure_all_channels)

        self.build_layout()
        self.connect_signals()
        self.set_controls_enabled(False)
        self.refresh_visa_resources()

    def build_layout(self):
        main_layout = QVBoxLayout()

        connection_layout = QGridLayout()
        connection_layout.addWidget(QLabel("VISA resource:"), 0, 0)
        connection_layout.addWidget(self.resource_input, 0, 1, 1, 3)

        connection_layout.addWidget(QLabel("Detected:"), 1, 0)
        connection_layout.addWidget(self.resource_combo, 1, 1)
        connection_layout.addWidget(self.refresh_button, 1, 2)
        connection_layout.addWidget(self.connect_button, 1, 3)

        connection_layout.addWidget(self.disconnect_button, 2, 3)
        connection_layout.addWidget(self.idn_label, 3, 0, 1, 4)

        main_layout.addLayout(connection_layout)

        channel_layout = QHBoxLayout()
        for ch in self.channels:
            channel_layout.addWidget(ch)

        main_layout.addLayout(channel_layout)

        utility_layout = QGridLayout()
        utility_layout.addWidget(self.reset_button, 0, 0)
        utility_layout.addWidget(self.clear_button, 0, 1)
        utility_layout.addWidget(self.error_button, 0, 2)
        utility_layout.addWidget(self.auto_measure_button, 0, 3)
        utility_layout.addWidget(self.error_label, 1, 0, 1, 4)

        main_layout.addLayout(utility_layout)

        self.setLayout(main_layout)

    def connect_signals(self):
        self.refresh_button.clicked.connect(self.refresh_visa_resources)
        self.connect_button.clicked.connect(self.connect_instrument)
        self.disconnect_button.clicked.connect(self.disconnect_instrument)

        self.reset_button.clicked.connect(self.reset_instrument)
        self.clear_button.clicked.connect(self.clear_errors)
        self.error_button.clicked.connect(self.read_error)
        self.auto_measure_button.clicked.connect(self.toggle_auto_measure)

        for ch_control in self.channels:
            ch_control.apply_button.clicked.connect(
                lambda checked, c=ch_control: self.apply_channel(c)
            )
            ch_control.on_button.clicked.connect(
                lambda checked, c=ch_control: self.output_on(c)
            )
            ch_control.off_button.clicked.connect(
                lambda checked, c=ch_control: self.output_off(c)
            )
            ch_control.measure_button.clicked.connect(
                lambda checked, c=ch_control: self.measure_channel(c)
            )

    def refresh_visa_resources(self):
        try:
            rm = pyvisa.ResourceManager()
            resources = rm.list_resources()
            rm.close()

            self.resource_combo.clear()
            self.resource_combo.addItems(resources)

            if resources:
                self.resource_input.setText(resources[0])

        except Exception as e:
            QMessageBox.critical(self, "VISA Error", str(e))

    def connect_instrument(self):
        resource = self.resource_input.text().strip()

        if not resource:
            resource = self.resource_combo.currentText().strip()

        if not resource:
            QMessageBox.warning(self, "No Resource", "No VISA resource selected.")
            return

        try:
            self.psu = KeysightE36312A(resource)
            idn = self.psu.idn()

            self.idn_label.setText(f"Instrument: {idn}")
            self.set_controls_enabled(True)

            self.connect_button.setEnabled(False)
            self.disconnect_button.setEnabled(True)

        except Exception as e:
            self.psu = None
            QMessageBox.critical(self, "Connection Error", str(e))

    def disconnect_instrument(self):
        self.timer.stop()
        self.auto_measure_enabled = False
        self.auto_measure_button.setText("Start Auto Measure")

        if self.psu is not None:
            try:
                self.psu.close()
            except Exception:
                pass

        self.psu = None
        self.idn_label.setText("Instrument: Not connected")

        self.set_controls_enabled(False)
        self.connect_button.setEnabled(True)
        self.disconnect_button.setEnabled(False)

    def set_controls_enabled(self, enabled):
        for ch in self.channels:
            ch.setEnabled(enabled)

        self.reset_button.setEnabled(enabled)
        self.clear_button.setEnabled(enabled)
        self.error_button.setEnabled(enabled)
        self.auto_measure_button.setEnabled(enabled)

    def apply_channel(self, ch_control):
        if not self.psu:
            return

        ch = ch_control.channel
        voltage = ch_control.voltage_spin.value()
        current = ch_control.current_spin.value()

        try:
            self.psu.set_channel(ch, voltage, current)
            ch_control.status_label.setText(
                f"Status: CH{ch} set to {voltage:.3f} V, {current:.3f} A"
            )
        except Exception as e:
            QMessageBox.critical(self, f"CH{ch} Error", str(e))

    def output_on(self, ch_control):
        if not self.psu:
            return

        ch = ch_control.channel

        try:
            self.psu.output_on(ch)
            ch_control.status_label.setText(f"Status: CH{ch} output ON")
        except Exception as e:
            QMessageBox.critical(self, f"CH{ch} Error", str(e))

    def output_off(self, ch_control):
        if not self.psu:
            return

        ch = ch_control.channel

        try:
            self.psu.output_off(ch)
            ch_control.status_label.setText(f"Status: CH{ch} output OFF")
        except Exception as e:
            QMessageBox.critical(self, f"CH{ch} Error", str(e))

    def measure_channel(self, ch_control):
        if not self.psu:
            return

        ch = ch_control.channel

        try:
            voltage = self.psu.measure_voltage(ch)
            current = self.psu.measure_current(ch)

            ch_control.measured_voltage_label.setText(
                f"Measured V: {voltage:.4f} V"
            )
            ch_control.measured_current_label.setText(
                f"Measured I: {current:.6f} A"
            )

        except Exception as e:
            QMessageBox.critical(self, f"CH{ch} Measurement Error", str(e))

    def measure_all_channels(self):
        for ch_control in self.channels:
            self.measure_channel(ch_control)

    def toggle_auto_measure(self):
        self.auto_measure_enabled = not self.auto_measure_enabled

        if self.auto_measure_enabled:
            self.timer.start()
            self.auto_measure_button.setText("Stop Auto Measure")
        else:
            self.timer.stop()
            self.auto_measure_button.setText("Start Auto Measure")

    def reset_instrument(self):
        if not self.psu:
            return

        try:
            self.psu.reset()
            self.error_label.setText("Error: Instrument reset complete")
        except Exception as e:
            QMessageBox.critical(self, "Reset Error", str(e))

    def clear_errors(self):
        if not self.psu:
            return

        try:
            self.psu.clear()
            self.error_label.setText("Error: Cleared")
        except Exception as e:
            QMessageBox.critical(self, "Clear Error", str(e))

    def read_error(self):
        if not self.psu:
            return

        try:
            err = self.psu.get_error()
            self.error_label.setText(f"Error: {err}")
        except Exception as e:
            QMessageBox.critical(self, "Read Error", str(e))

    def closeEvent(self, event):
        self.disconnect_instrument()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    gui = PowerSupplyGUI()
    gui.resize(1100, 450)
    gui.show()

    sys.exit(app.exec_())