# -*- coding: utf-8 -*-
"""
YBCO Auto Sweep Control Panel
==============================
Launch the unified GUI for Laser, LakeShore 335, and VNA control.

Design: Deep Space Cyan (极简深色模式仪表板)
Usage:
    python app.py

Requirements:
    pip install pyqt5 pyvisa
"""

import sys
from PyQt5.QtWidgets import QApplication
from ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # ==================================================================
    # Deep Space Cyan — global QSS theme
    # ==================================================================
    app.setStyleSheet("""
        /* ---- base ---- */
        QMainWindow, QWidget {
            background-color: #0C1014;
            color: #E6EDF3;
        }

        /* ---- cards / sections ---- */
        QGroupBox {
            background-color: #161B22;
            border: 1px solid rgba(255, 255, 255, 0.10);
            border-radius: 8px;
            margin-top: 18px;
            padding-top: 20px;
            font-weight: bold;
            color: #8B949E;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 14px;
            padding: 0 8px;
            color: #E6EDF3;
            font-size: 13px;
        }

        /* ---- buttons ---- */
        QPushButton {
            background-color: #21262D;
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 8px;
            padding: 8px 18px;
            color: #E6EDF3;
            font-weight: bold;
            min-height: 20px;
        }
        QPushButton:hover {
            background-color: #30363D;
            border-color: #22D3EE;
        }
        QPushButton:pressed {
            background-color: #1C2128;
            border-color: #06B6D4;
        }
        QPushButton:disabled {
            background-color: #161B22;
            color: #484F58;
            border-color: rgba(255,255,255,0.06);
        }

        /* ---- inputs ---- */
        QLineEdit, QDoubleSpinBox, QSpinBox {
            background-color: #0C1014;
            border: 1px solid #30363D;
            border-radius: 6px;
            padding: 6px 8px;
            color: #E6EDF3;
        }
        QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus {
            border-color: #22D3EE;
        }

        /* ---- combobox ---- */
        QComboBox {
            background-color: #21262D;
            border: 1px solid #30363D;
            border-radius: 6px;
            padding: 6px 10px;
            color: #E6EDF3;
        }
        QComboBox:hover {
            border-color: #22D3EE;
        }
        QComboBox::drop-down {
            border: none;
            width: 22px;
        }
        QComboBox QAbstractItemView {
            background-color: #21262D;
            border: 1px solid #30363D;
            color: #E6EDF3;
            selection-background-color: #22D3EE;
            selection-color: #0C1014;
            outline: none;
        }

        /* ---- log / text edit ---- */
        QTextEdit {
            background-color: #0C1014;
            border: 1px solid #30363D;
            border-radius: 6px;
            color: #8B949E;
            font-family: "JetBrains Mono", "Consolas", "Courier New", monospace;
            font-size: 11px;
        }

        /* ---- labels ---- */
        QLabel {
            color: #E6EDF3;
            background: transparent;
        }

        /* ---- radio buttons ---- */
        QRadioButton {
            color: #E6EDF3;
            spacing: 6px;
        }
        QRadioButton::indicator {
            width: 16px;
            height: 16px;
            border-radius: 9px;
            border: 2px solid #30363D;
            background-color: #0C1014;
        }
        QRadioButton::indicator:checked {
            border-color: #22D3EE;
            background-color: #22D3EE;
        }

        /* ---- scrollbars ---- */
        QScrollBar:vertical {
            background: #0C1014;
            width: 8px;
            border-radius: 4px;
        }
        QScrollBar::handle:vertical {
            background: #30363D;
            border-radius: 4px;
            min-height: 24px;
        }
        QScrollBar::handle:vertical:hover {
            background: #22D3EE;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }

        /* ---- tooltips ---- */
        QToolTip {
            background-color: #21262D;
            color: #E6EDF3;
            border: 1px solid #30363D;
            border-radius: 4px;
            padding: 4px 8px;
        }
    """)

    win = MainWindow()
    win.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
