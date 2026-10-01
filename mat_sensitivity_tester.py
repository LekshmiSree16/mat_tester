import sys
import os
import csv
from datetime import datetime
import numpy as np

from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QComboBox, QPushButton, QLabel, QGroupBox,
                               QSpinBox, QDoubleSpinBox, QLineEdit, QSplitter, QFrame,
                               QFileDialog, QButtonGroup, QRadioButton)
from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QFont

import pyqtgraph as pg

# Local imports
from connection_manager import IsolatedConnectionManager
from pressure_map import PressureHeatmapWidget


class MatSensitivityTesterApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Luxisens Optical Fiber Mat Sensitivity Tester")
        self.resize(1380, 880)
        self.setMinimumSize(1100, 750)

        # 1. Hardware Connection Manager
        self.conn = IsolatedConnectionManager()
        self.conn.new_frame_signal.connect(self.handle_new_frame)
        self.conn.connection_status_signal.connect(self.handle_connection_status)

        # Buffer limits (500 samples = 10 seconds at 50Hz)
        self.history_size = 500
        self.raw_history = np.zeros((40, self.history_size))
        self.calibrated_history = np.zeros((40, self.history_size))
        self.selected_channel = 0
        self.current_max_scale = 32000

        # Zero-Calibration State
        self.is_calibrating = False
        self.calibration_buffer = []
        self.baseline = None

        # Sensitivity Test State
        self.test_no_load_val = 0.0
        self.test_loaded_val = 0.0
        self.test_sensitivity_val = 0.0
        self.test_pressure_sens_g_cm2 = 0.0
        self.test_pressure_sens_kpa = 0.0
        self.tested_channels_data = []
        self.sensitivity_array = np.zeros(40)

        # Performance metric tracking
        self.packet_count = 0
        self.fps_packet_count = 0
        self.last_fps_time = datetime.now()
        self.current_freq_hz = 0.0

        # 2. Setup the Streamlined User Interface
        self.setup_ui()
        self.populate_serial_ports()
        self.recalculate_area_and_pressure()

        # Connect theme styles
        self.apply_dark_theme()

        # 3. Decoupled UI Refresh Timer (20 FPS)
        self.ui_timer = QTimer(self)
        self.ui_timer.timeout.connect(self.refresh_ui_elements)
        self.ui_timer.start(50)

        # Data rate timer (1 second)
        self.sec_timer = QTimer(self)
        self.sec_timer.timeout.connect(self.calculate_data_rate)
        self.sec_timer.start(1000)

    def populate_serial_ports(self):
        self.cb_ports.clear()
        ports = self.conn.get_ports()
        if ports:
            self.cb_ports.addItems(ports)
            for i, p in enumerate(ports):
                if "3752" in p.upper() or "374B" in p.upper() or "STM" in p.upper():
                    self.cb_ports.setCurrentIndex(i)
                    break
        else:
            self.cb_ports.addItem("No COM ports found")

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # ==========================================
        # 1. HEADER SECTION (Connection metrics)
        # ==========================================
        header_widget = QFrame()
        header_widget.setObjectName("HeaderCard")
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(15, 10, 15, 10)

        title_lbl = QLabel("LUXISENS OPTICAL FIBER MAT SENSITIVITY TESTER")
        title_lbl.setStyleSheet("font-size: 19px; font-weight: bold; color: #00ff9d; letter-spacing: 1px;")

        self.lbl_conn_status = QLabel("DISCONNECTED")
        self.lbl_conn_status.setObjectName("StatusDisconnected")
        self.lbl_conn_status.setAlignment(Qt.AlignCenter)
        self.lbl_conn_status.setFixedWidth(160)
        self.lbl_conn_status.setFixedHeight(30)

        self.lbl_hz = QLabel("Data Rate: 0.0 Hz")
        self.lbl_hz.setStyleSheet("font-size: 13px; color: #aaa; font-family: monospace;")

        self.lbl_packets = QLabel("Packets Rx: 0")
        self.lbl_packets.setStyleSheet("font-size: 13px; color: #aaa; font-family: monospace;")

        header_layout.addWidget(title_lbl)
        header_layout.addStretch()
        header_layout.addWidget(self.lbl_hz)
        header_layout.addWidget(self.lbl_packets)
        header_layout.addWidget(self.lbl_conn_status)
        main_layout.addWidget(header_widget)

        # ==========================================
        # 2. MAIN BODY (Left Column & Right Column)
        # ==========================================
        body_splitter = QSplitter(Qt.Horizontal)

        # ------------------------------------------
        # LEFT COLUMN: Connection & Physical Mat Map
        # ------------------------------------------
        left_col = QWidget()
        left_layout = QVBoxLayout(left_col)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        # Group: Hardware Interface Settings
        conn_group = QGroupBox("Hardware Interface Settings")
        conn_layout = QVBoxLayout(conn_group)
        conn_layout.setSpacing(8)

        # Mode select
        mode_lay = QHBoxLayout()
        lbl_mode = QLabel("Interface Source:")
        lbl_mode.setFixedWidth(120)
        self.cb_mode = QComboBox()
        self.cb_mode.addItems(["Serial (COM Port)", "Wi-Fi (DataGram-6060)", "Live Simulator"])
        self.cb_mode.currentIndexChanged.connect(self.on_mode_changed)
        mode_lay.addWidget(lbl_mode)
        mode_lay.addWidget(self.cb_mode, 1)
        conn_layout.addLayout(mode_lay)

        # Serial Settings Container
        self.serial_settings_widget = QWidget()
        serial_lay = QVBoxLayout(self.serial_settings_widget)
        serial_lay.setContentsMargins(0, 0, 0, 0)
        serial_lay.setSpacing(6)

        port_lay = QHBoxLayout()
        lbl_port = QLabel("COM Port:")
        lbl_port.setFixedWidth(120)
        self.cb_ports = QComboBox()
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setFixedWidth(65)
        self.btn_refresh.clicked.connect(self.populate_serial_ports)
        port_lay.addWidget(lbl_port)
        port_lay.addWidget(self.cb_ports, 1)
        port_lay.addWidget(self.btn_refresh)
        serial_lay.addLayout(port_lay)

        baud_lay = QHBoxLayout()
        lbl_baud = QLabel("Baud Rate:")
        lbl_baud.setFixedWidth(120)
        self.cb_baud = QComboBox()
        self.cb_baud.addItems(["921600", "460800", "115200", "9600"])
        baud_lay.addWidget(lbl_baud)
        baud_lay.addWidget(self.cb_baud, 1)
        serial_lay.addLayout(baud_lay)
        conn_layout.addWidget(self.serial_settings_widget)

        # UDP Settings Container
        self.udp_settings_widget = QWidget()
        self.udp_settings_widget.setVisible(False)
        udp_lay = QHBoxLayout(self.udp_settings_widget)
        udp_lay.setContentsMargins(0, 0, 0, 0)
        lbl_udp = QLabel("DataGram Port:")
        lbl_udp.setFixedWidth(120)
        self.txt_udp_port = QLineEdit("6060")
        udp_lay.addWidget(lbl_udp)
        udp_lay.addWidget(self.txt_udp_port, 1)
        conn_layout.addWidget(self.udp_settings_widget)

        # Mat Light Sensitivity (INTT)
        sens_lay = QHBoxLayout()
        lbl_sens = QLabel("Mat Light Sens (INTT):")
        lbl_sens.setFixedWidth(120)
        self.cb_sens_hw = QComboBox()
        self.cb_sens_hw.addItems(["50", "100", "500", "1000", "1500", "2000", "3000"])
        self.cb_sens_hw.setCurrentIndex(2)  # Default 500
        self.cb_sens_hw.currentIndexChanged.connect(self.on_hw_sensitivity_changed)
        sens_lay.addWidget(lbl_sens)
        sens_lay.addWidget(self.cb_sens_hw, 1)
        conn_layout.addLayout(sens_lay)

        # Connect & Zero Calibrate Buttons
        btn_lay = QHBoxLayout()
        self.btn_connect = QPushButton("CONNECT")
        self.btn_connect.setObjectName("BtnConnect")
        self.btn_connect.setFixedHeight(28)
        self.btn_connect.clicked.connect(self.toggle_connection)

        self.btn_calibrate = QPushButton("Zero Calibrate")
        self.btn_calibrate.setObjectName("BtnCalibrate")
        self.btn_calibrate.setFixedHeight(28)
        self.btn_calibrate.clicked.connect(self.start_calibration)
        self.btn_calibrate.setEnabled(False)

        btn_lay.addWidget(self.btn_connect)
        btn_lay.addWidget(self.btn_calibrate)
        conn_layout.addLayout(btn_lay)

        self.lbl_calib_indicator = QLabel("")
        self.lbl_calib_indicator.setAlignment(Qt.AlignCenter)
        self.lbl_calib_indicator.setStyleSheet("color: #ff9d00; font-weight: bold; font-size: 11px;")
        conn_layout.addWidget(self.lbl_calib_indicator)

        left_layout.addWidget(conn_group)

        # Group: Physical Mattress Heatmap
        map_group = QGroupBox("Mattress Layout (Physical 8×5 Grid)")
        map_layout = QVBoxLayout(map_group)
        map_layout.setContentsMargins(10, 8, 10, 8)
        map_layout.setSpacing(6)

        # Map display mode toggles
        map_mode_lay = QHBoxLayout()
        lbl_view = QLabel("Map Mode:")
        lbl_view.setStyleSheet("font-weight: bold; color: #888; font-size: 11px;")
        self.rb_mode_live = QRadioButton("Live Pressure")
        self.rb_mode_sens = QRadioButton("Sensitivity Report")
        self.rb_mode_live.setChecked(True)
        self.rb_mode_live.toggled.connect(self.on_map_mode_toggled)

        self.map_mode_group = QButtonGroup(self)
        self.map_mode_group.addButton(self.rb_mode_live)
        self.map_mode_group.addButton(self.rb_mode_sens)

        map_mode_lay.addWidget(lbl_view)
        map_mode_lay.addWidget(self.rb_mode_live)
        map_mode_lay.addWidget(self.rb_mode_sens)
        map_mode_lay.addStretch()
        map_layout.addLayout(map_mode_lay)

        # Heatmap Widget (Single clean physical swapped layout)
        self.heatmap = PressureHeatmapWidget("Mattress Physical Layout", use_swapped_layout=True, cell_size=56, is_patient_monitor_style=False)
        self.heatmap.sensor_selected.connect(self.change_selected_channel)
        map_layout.addWidget(self.heatmap, 0, Qt.AlignCenter)

        lbl_hint = QLabel("💡 Tip: Click any cell to select that channel for sensitivity testing.")
        lbl_hint.setStyleSheet("color: #777; font-size: 11px; font-style: italic;")
        lbl_hint.setAlignment(Qt.AlignCenter)
        map_layout.addWidget(lbl_hint)

        left_layout.addWidget(map_group, 1)
        body_splitter.addWidget(left_col)

        # ------------------------------------------
        # RIGHT COLUMN: Sensitivity Test Controls & Settling Plot
        # ------------------------------------------
        right_col = QWidget()
        right_layout = QVBoxLayout(right_col)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        # Panel 1: Sensitivity Test Controls
        sens_panel_group = QGroupBox("Sensitivity Test Controls")
        sens_panel_layout = QVBoxLayout(sens_panel_group)
        sens_panel_layout.setContentsMargins(12, 10, 12, 10)
        sens_panel_layout.setSpacing(10)

        # Row 1: Channel selection & Tested progress
        row_ch_lay = QHBoxLayout()
        lbl_ch_sel = QLabel("Active Channel:")
        lbl_ch_sel.setStyleSheet("font-weight: bold; color: #fff; font-size: 13px;")

        self.sp_channel = QSpinBox()
        self.sp_channel.setRange(0, 39)
        self.sp_channel.setValue(0)
        self.sp_channel.setFixedWidth(65)
        self.sp_channel.setFixedHeight(26)
        self.sp_channel.valueChanged.connect(self.change_selected_channel)

        self.lbl_tested_counter = QLabel("Tested: 0 / 40 channels")
        self.lbl_tested_counter.setStyleSheet("color: #00d4ff; font-weight: bold; font-family: monospace; font-size: 12px;")

        row_ch_lay.addWidget(lbl_ch_sel)
        row_ch_lay.addWidget(self.sp_channel)
        row_ch_lay.addSpacing(20)
        row_ch_lay.addWidget(self.lbl_tested_counter)
        row_ch_lay.addStretch()
        sens_panel_layout.addLayout(row_ch_lay)

        # Row 2: Weight & Base Dimensions Inputs
        row_inputs = QHBoxLayout()
        lbl_weight = QLabel("Applied Weight (g):")
        lbl_weight.setStyleSheet("font-weight: bold; color: #aaa;")
        self.sp_weight = QSpinBox()
        self.sp_weight.setRange(1, 100000)
        self.sp_weight.setValue(500)
        self.sp_weight.setFixedHeight(26)
        self.sp_weight.valueChanged.connect(self.on_weight_or_dim_changed)

        lbl_dims = QLabel("Base Dimensions (L × B mm):")
        lbl_dims.setStyleSheet("font-weight: bold; color: #aaa;")

        dim_widget = QWidget()
        dim_lay = QHBoxLayout(dim_widget)
        dim_lay.setContentsMargins(0, 0, 0, 0)
        dim_lay.setSpacing(4)

        self.sp_length = QDoubleSpinBox()
        self.sp_length.setRange(0.1, 1000.0)
        self.sp_length.setValue(36.0)
        self.sp_length.setDecimals(1)
        self.sp_length.setFixedWidth(65)
        self.sp_length.setFixedHeight(26)
        self.sp_length.valueChanged.connect(self.on_weight_or_dim_changed)

        lbl_mul = QLabel("×")
        lbl_mul.setStyleSheet("color: #888; font-weight: bold;")

        self.sp_breadth = QDoubleSpinBox()
        self.sp_breadth.setRange(0.1, 1000.0)
        self.sp_breadth.setValue(26.0)
        self.sp_breadth.setDecimals(1)
        self.sp_breadth.setFixedWidth(65)
        self.sp_breadth.setFixedHeight(26)
        self.sp_breadth.valueChanged.connect(self.on_weight_or_dim_changed)

        dim_lay.addWidget(self.sp_length)
        dim_lay.addWidget(lbl_mul)
        dim_lay.addWidget(self.sp_breadth)

        row_inputs.addWidget(lbl_weight)
        row_inputs.addWidget(self.sp_weight)
        row_inputs.addSpacing(15)
        row_inputs.addWidget(lbl_dims)
        row_inputs.addWidget(dim_widget)
        row_inputs.addStretch()
        sens_panel_layout.addLayout(row_inputs)

        # Row 3: Computed Area and Pressure
        row_calc = QHBoxLayout()
        self.lbl_area_val = QLabel("Area: 9.36 cm² (936 mm²)")
        self.lbl_applied_pressure = QLabel("Pressure: 53.4 g/cm² (5.24 kPa)")
        for lbl in [self.lbl_area_val, self.lbl_applied_pressure]:
            lbl.setStyleSheet("color: #00d4ff; font-size: 13px; font-weight: bold; font-family: monospace;")
        row_calc.addWidget(self.lbl_area_val)
        row_calc.addSpacing(25)
        row_calc.addWidget(self.lbl_applied_pressure)
        row_calc.addStretch()
        sens_panel_layout.addLayout(row_calc)

        # Row 4: Capture & File Buttons
        btn_action_lay = QHBoxLayout()
        btn_action_lay.setSpacing(10)
        self.btn_capture_noload = QPushButton("1. Capture No-Load Baseline")
        self.btn_capture_noload.clicked.connect(self.capture_no_load)
        self.btn_capture_noload.setFixedHeight(30)

        self.btn_capture_loaded = QPushButton("2. Capture Loaded Value")
        self.btn_capture_loaded.clicked.connect(self.capture_loaded)
        self.btn_capture_loaded.setFixedHeight(30)

        self.btn_save_report = QPushButton("Save Report (CSV)")
        self.btn_save_report.clicked.connect(self.save_sensitivity_report)
        self.btn_save_report.setFixedHeight(30)
        self.btn_save_report.setStyleSheet("background-color: #0088ff; font-weight: bold;")

        self.btn_load_report = QPushButton("Load Report (CSV)")
        self.btn_load_report.clicked.connect(self.load_sensitivity_report)
        self.btn_load_report.setFixedHeight(30)
        self.btn_load_report.setStyleSheet("background-color: #333333; font-weight: bold;")

        btn_action_lay.addWidget(self.btn_capture_noload)
        btn_action_lay.addWidget(self.btn_capture_loaded)
        btn_action_lay.addWidget(self.btn_save_report)
        btn_action_lay.addWidget(self.btn_load_report)
        sens_panel_layout.addLayout(btn_action_lay)

        # Row 5: Intermediate Values Cards
        card_box = QFrame()
        card_box.setStyleSheet("background-color: #1a1a1a; border: 1px solid #282828; border-radius: 6px; padding: 6px;")
        card_lay = QHBoxLayout(card_box)
        card_lay.setContentsMargins(10, 5, 10, 5)

        self.lbl_sens_ch = QLabel(f"Selected: Ch {self.selected_channel}")
        self.lbl_sens_noload = QLabel("No-Load Avg: --")
        self.lbl_sens_loaded = QLabel("Loaded Avg: --")
        self.lbl_sens_diff = QLabel("Difference: --")
        for lbl in [self.lbl_sens_ch, self.lbl_sens_noload, self.lbl_sens_loaded, self.lbl_sens_diff]:
            lbl.setStyleSheet("color: #ccc; font-size: 13px; font-weight: bold; font-family: monospace;")

        card_lay.addWidget(self.lbl_sens_ch)
        card_lay.addStretch()
        card_lay.addWidget(self.lbl_sens_noload)
        card_lay.addStretch()
        card_lay.addWidget(self.lbl_sens_loaded)
        card_lay.addStretch()
        card_lay.addWidget(self.lbl_sens_diff)
        sens_panel_layout.addWidget(card_box)

        # Row 6: Final Calculated Sensitivities (Highlighted)
        res_box = QFrame()
        res_box.setStyleSheet("background-color: #18261e; border: 1px solid #00aa66; border-radius: 6px; padding: 8px;")
        res_lay = QHBoxLayout(res_box)
        res_lay.setContentsMargins(12, 6, 12, 6)

        self.lbl_sens_val = QLabel("Mass Sensitivity: -- units/g")
        self.lbl_sens_val.setStyleSheet("color: #00ff9d; font-size: 14px; font-weight: bold; font-family: monospace;")

        self.lbl_sens_pressure = QLabel("Pressure Sensitivity: -- units/(g/cm²) | -- units/kPa")
        self.lbl_sens_pressure.setStyleSheet("color: #00ff9d; font-size: 14px; font-weight: bold; font-family: monospace;")

        res_lay.addWidget(self.lbl_sens_val)
        res_lay.addStretch()
        res_lay.addWidget(self.lbl_sens_pressure)
        sens_panel_layout.addWidget(res_box)

        right_layout.addWidget(sens_panel_group)

        # Panel 2: Live Signal Settling Plot
        plot_group = QGroupBox("Live Channel Signal Settling Trace (Ensure Signal is Settled Before Capture)")
        plot_layout = QVBoxLayout(plot_group)
        plot_layout.setContentsMargins(8, 8, 8, 8)

        pg.setConfigOption('background', '#151515')
        pg.setConfigOption('foreground', '#d0d0d0')

        self.plot_time = pg.PlotWidget(title=f"Channel {self.selected_channel} Optical Response")
        self.plot_time.setLabel('left', 'Optical Signal (ADC Counts)')
        self.plot_time.setLabel('bottom', 'Samples (Last 10 Seconds at 50Hz)')
        self.plot_time.showGrid(x=True, y=True, alpha=0.3)
        self.time_curve = self.plot_time.plot(pen=pg.mkPen(color='#00ff9d', width=2))
        plot_layout.addWidget(self.plot_time)

        right_layout.addWidget(plot_group, 1)

        body_splitter.addWidget(right_col)
        body_splitter.setStretchFactor(0, 0)
        body_splitter.setStretchFactor(1, 1)
        main_layout.addWidget(body_splitter, 1)

    # ==========================================
    # Logic: Area & Pressure Calculations
    # ==========================================
    def recalculate_area_and_pressure(self):
        weight = self.sp_weight.value()
        length_mm = self.sp_length.value()
        breadth_mm = self.sp_breadth.value()

        area_mm2 = length_mm * breadth_mm
        area_cm2 = area_mm2 / 100.0
        area_m2 = area_mm2 / 1_000_000.0

        self.lbl_area_val.setText(f"Area: {area_cm2:.2f} cm² ({area_mm2:.0f} mm²)")

        if area_cm2 > 0 and weight > 0:
            pressure_g_cm2 = weight / area_cm2
            force_n = (weight / 1000.0) * 9.80665
            pressure_kpa = (force_n / area_m2) / 1000.0
        else:
            pressure_g_cm2 = 0.0
            pressure_kpa = 0.0

        self.lbl_applied_pressure.setText(f"Pressure: {pressure_g_cm2:.1f} g/cm² ({pressure_kpa:.2f} kPa)")
        return weight, length_mm, breadth_mm, area_cm2, pressure_g_cm2, pressure_kpa

    def on_weight_or_dim_changed(self):
        if self.test_loaded_val != 0.0 or self.test_no_load_val != 0.0:
            self.update_sensitivity_calc()
        else:
            self.recalculate_area_and_pressure()

    def get_current_channel_average(self):
        active_buffer = self.calibrated_history if self.baseline is not None else self.raw_history
        recent_window = active_buffer[self.selected_channel, -50:]
        return float(np.mean(recent_window))

    def capture_no_load(self):
        self.test_no_load_val = self.get_current_channel_average()
        self.lbl_sens_noload.setText(f"No-Load Avg: {self.test_no_load_val:.1f}")
        self.update_sensitivity_calc()

    def capture_loaded(self):
        self.test_loaded_val = self.get_current_channel_average()
        self.lbl_sens_loaded.setText(f"Loaded Avg: {self.test_loaded_val:.1f}")
        self.update_sensitivity_calc()

    def update_sensitivity_calc(self):
        weight, length_mm, breadth_mm, area_cm2, pressure_g_cm2, pressure_kpa = self.recalculate_area_and_pressure()
        diff = self.test_loaded_val - self.test_no_load_val

        self.test_sensitivity_val = diff / weight if weight > 0 else 0.0
        self.test_pressure_sens_g_cm2 = diff / pressure_g_cm2 if pressure_g_cm2 > 0 else 0.0
        self.test_pressure_sens_kpa = diff / pressure_kpa if pressure_kpa > 0 else 0.0

        self.lbl_sens_diff.setText(f"Difference: {diff:.1f}")
        self.lbl_sens_val.setText(f"Mass Sensitivity: {self.test_sensitivity_val:.3f} units/g")
        self.lbl_sens_pressure.setText(f"Pressure Sensitivity: {self.test_pressure_sens_g_cm2:.2f} units/(g/cm²) | {self.test_pressure_sens_kpa:.1f} units/kPa")

        record = {
            'Channel': self.selected_channel,
            'Weight': weight,
            'Length_mm': length_mm,
            'Breadth_mm': breadth_mm,
            'Area_cm2': area_cm2,
            'Pressure_g_cm2': pressure_g_cm2,
            'Pressure_kPa': pressure_kpa,
            'NoLoad': self.test_no_load_val,
            'Loaded': self.test_loaded_val,
            'Diff': diff,
            'Sensitivity': self.test_sensitivity_val,
            'Sensitivity_g_cm2': self.test_pressure_sens_g_cm2,
            'Sensitivity_kPa': self.test_pressure_sens_kpa
        }
        self.tested_channels_data = [r for r in self.tested_channels_data if r['Channel'] != self.selected_channel]
        self.tested_channels_data.append(record)
        self.sensitivity_array[self.selected_channel] = self.test_sensitivity_val

        self.lbl_tested_counter.setText(f"Tested: {len(self.tested_channels_data)} / 40 channels")

        if self.rb_mode_sens.isChecked():
            self.update_sensitivity_map()

    def update_sensitivity_map(self):
        max_sens = float(np.max(self.sensitivity_array))
        if max_sens <= 0.0:
            max_sens = 1.0
        self.heatmap.update_data(self.sensitivity_array.tolist(), max_val=max_sens)

    def on_map_mode_toggled(self):
        if self.rb_mode_sens.isChecked():
            self.update_sensitivity_map()

    def change_selected_channel(self, val):
        self.selected_channel = val
        self.sp_channel.blockSignals(True)
        self.sp_channel.setValue(val)
        self.sp_channel.blockSignals(False)

        self.heatmap.blockSignals(True)
        self.heatmap.select_sensor_programmatically(val)
        self.heatmap.blockSignals(False)

        self.lbl_sens_ch.setText(f"Selected: Ch {val}")

        # If this channel was previously tested, restore its values!
        prev = next((r for r in self.tested_channels_data if r['Channel'] == val), None)
        if prev:
            self.test_no_load_val = prev['NoLoad']
            self.test_loaded_val = prev['Loaded']
            self.test_sensitivity_val = prev['Sensitivity']
            self.test_pressure_sens_g_cm2 = prev.get('Sensitivity_g_cm2', 0.0)
            self.test_pressure_sens_kpa = prev.get('Sensitivity_kPa', 0.0)

            self.lbl_sens_noload.setText(f"No-Load Avg: {self.test_no_load_val:.1f}")
            self.lbl_sens_loaded.setText(f"Loaded Avg: {self.test_loaded_val:.1f}")
            self.lbl_sens_diff.setText(f"Difference: {prev['Diff']:.1f}")
            self.lbl_sens_val.setText(f"Mass Sensitivity: {self.test_sensitivity_val:.3f} units/g")
            self.lbl_sens_pressure.setText(f"Pressure Sensitivity: {self.test_pressure_sens_g_cm2:.2f} units/(g/cm²) | {self.test_pressure_sens_kpa:.1f} units/kPa")
        else:
            self.test_no_load_val = 0.0
            self.test_loaded_val = 0.0
            self.test_sensitivity_val = 0.0
            self.test_pressure_sens_g_cm2 = 0.0
            self.test_pressure_sens_kpa = 0.0
            self.lbl_sens_noload.setText("No-Load Avg: --")
            self.lbl_sens_loaded.setText("Loaded Avg: --")
            self.lbl_sens_diff.setText("Difference: --")
            self.lbl_sens_val.setText("Mass Sensitivity: -- units/g")
            self.lbl_sens_pressure.setText("Pressure Sensitivity: -- units/(g/cm²) | -- units/kPa")

    def save_sensitivity_report(self):
        if not self.tested_channels_data:
            print("No sensitivity data to save.")
            return

        os.makedirs("mat_logs", exist_ok=True)
        filename = f"mat_logs/SensitivityReport_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        try:
            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'Channel', 'Weight (g)', 'Base L (mm)', 'Base B (mm)', 'Area (cm2)',
                    'Pressure (g/cm2)', 'Pressure (kPa)', 'No Load Avg', 'Loaded Avg',
                    'Difference', 'Sensitivity (units/g)', 'Sensitivity (units/(g/cm2))', 'Sensitivity (units/kPa)'
                ])
                sorted_data = sorted(self.tested_channels_data, key=lambda x: x['Channel'])
                for r in sorted_data:
                    writer.writerow([
                        r['Channel'],
                        r['Weight'],
                        f"{r.get('Length_mm', 0):.1f}",
                        f"{r.get('Breadth_mm', 0):.1f}",
                        f"{r.get('Area_cm2', 0):.2f}",
                        f"{r.get('Pressure_g_cm2', 0):.2f}",
                        f"{r.get('Pressure_kPa', 0):.2f}",
                        f"{r['NoLoad']:.1f}",
                        f"{r['Loaded']:.1f}",
                        f"{r['Diff']:.1f}",
                        f"{r['Sensitivity']:.3f}",
                        f"{r.get('Sensitivity_g_cm2', 0):.2f}",
                        f"{r.get('Sensitivity_kPa', 0):.1f}"
                    ])
            print(f"Report saved to {filename}")
        except Exception as e:
            print(f"Failed to save report: {e}")

    def load_sensitivity_report(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Open Sensitivity Report", "mat_logs", "CSV Files (*.csv)")
        if file_name:
            try:
                with open(file_name, 'r') as f:
                    reader = csv.DictReader(f)
                    self.tested_channels_data = []
                    self.sensitivity_array = np.zeros(40)
                    for row in reader:
                        ch = int(row['Channel'])
                        weight = float(row['Weight (g)'])
                        noload = float(row['No Load Avg'])
                        loaded = float(row['Loaded Avg'])
                        diff = float(row['Difference'])
                        sens = float(row['Sensitivity (units/g)'])

                        length_mm = float(row['Base L (mm)']) if 'Base L (mm)' in row else 36.0
                        breadth_mm = float(row['Base B (mm)']) if 'Base B (mm)' in row else 26.0
                        area_cm2 = float(row['Area (cm2)']) if 'Area (cm2)' in row else (length_mm * breadth_mm / 100.0)

                        if 'Pressure (g/cm2)' in row:
                            pressure_g_cm2 = float(row['Pressure (g/cm2)'])
                        else:
                            pressure_g_cm2 = weight / area_cm2 if area_cm2 > 0 else 0.0

                        if 'Pressure (kPa)' in row:
                            pressure_kpa = float(row['Pressure (kPa)'])
                        else:
                            pressure_kpa = ((weight / 1000.0) * 9.80665) / (area_cm2 * 1e-4) / 1000.0 if area_cm2 > 0 else 0.0

                        sens_g_cm2 = float(row['Sensitivity (units/(g/cm2))']) if 'Sensitivity (units/(g/cm2))' in row else (diff / pressure_g_cm2 if pressure_g_cm2 > 0 else 0.0)
                        sens_kpa = float(row['Sensitivity (units/kPa)']) if 'Sensitivity (units/kPa)' in row else (diff / pressure_kpa if pressure_kpa > 0 else 0.0)

                        record = {
                            'Channel': ch,
                            'Weight': weight,
                            'Length_mm': length_mm,
                            'Breadth_mm': breadth_mm,
                            'Area_cm2': area_cm2,
                            'Pressure_g_cm2': pressure_g_cm2,
                            'Pressure_kPa': pressure_kpa,
                            'NoLoad': noload,
                            'Loaded': loaded,
                            'Diff': diff,
                            'Sensitivity': sens,
                            'Sensitivity_g_cm2': sens_g_cm2,
                            'Sensitivity_kPa': sens_kpa
                        }
                        self.tested_channels_data.append(record)
                        if 0 <= ch < 40:
                            self.sensitivity_array[ch] = sens

                self.lbl_tested_counter.setText(f"Tested: {len(self.tested_channels_data)} / 40 channels")
                self.rb_mode_sens.setChecked(True)
                self.update_sensitivity_map()
                self.change_selected_channel(self.selected_channel)
                print(f"Loaded {len(self.tested_channels_data)} records from {file_name}")
            except Exception as e:
                print(f"Failed to load CSV: {e}")

    # ==========================================
    # Connection & Calibration Handlers
    # ==========================================
    def on_mode_changed(self, idx):
        if idx == 0:
            self.serial_settings_widget.setVisible(True)
            self.udp_settings_widget.setVisible(False)
        elif idx == 1:
            self.serial_settings_widget.setVisible(False)
            self.udp_settings_widget.setVisible(True)
        else:
            self.serial_settings_widget.setVisible(False)
            self.udp_settings_widget.setVisible(False)

    def on_hw_sensitivity_changed(self):
        val = self.cb_sens_hw.currentText()
        if self.conn.running:
            self.conn.send_command(f"AT+INTT {val}")

    def toggle_connection(self):
        if self.conn.running:
            self.conn.stop()
            self.btn_calibrate.setEnabled(False)
        else:
            mode_idx = self.cb_mode.currentIndex()
            success = False
            if mode_idx == 0:
                port = self.cb_ports.currentText().split(" ")[0].strip()
                baud = int(self.cb_baud.currentText())
                success = self.conn.start_serial(port, baud)
            elif mode_idx == 1:
                try:
                    port = int(self.txt_udp_port.text().strip())
                    success = self.conn.start_udp(port)
                except ValueError:
                    print("Invalid UDP port number")
                    return
            else:
                success = self.conn.start_simulator()

            if not success:
                print("Failed to start interface.")

    @Slot(bool, str)
    def handle_connection_status(self, is_connected, msg):
        if is_connected:
            self.lbl_conn_status.setText("ACTIVE")
            self.lbl_conn_status.setStyleSheet("background-color: #00ff9d; color: #111; font-weight: bold; border-radius: 4px;")
            self.btn_connect.setText("DISCONNECT")
            self.btn_connect.setStyleSheet("background-color: #ff3333; color: #fff; font-weight: bold;")
            self.btn_calibrate.setEnabled(True)
            QTimer.singleShot(1500 if self.cb_mode.currentIndex() == 0 else 500,
                              lambda: self.conn.send_command(f"AT+INTT {self.cb_sens_hw.currentText()}"))
        else:
            self.lbl_conn_status.setText("DISCONNECTED")
            self.lbl_conn_status.setStyleSheet("background-color: #ff3333; color: #fff; font-weight: bold; border-radius: 4px;")
            self.btn_connect.setText("CONNECT")
            self.btn_connect.setStyleSheet("background-color: #0088ff; color: #fff; font-weight: bold;")
            self.btn_calibrate.setEnabled(False)

    def start_calibration(self):
        if not self.conn.running:
            return
        self.is_calibrating = True
        self.calibration_buffer = []
        self.lbl_calib_indicator.setText("ZERO-CALIBRATING... (Keep mat undisturbed)")
        self.btn_calibrate.setEnabled(False)

    def finish_calibration(self):
        self.is_calibrating = False
        if self.calibration_buffer:
            self.baseline = np.mean(np.array(self.calibration_buffer), axis=0)
            self.lbl_calib_indicator.setText("ZERO CALIBRATED APPLIED")
        else:
            self.lbl_calib_indicator.setText("CALIBRATION FAILED")
        self.btn_calibrate.setEnabled(True)
        QTimer.singleShot(3000, lambda: self.lbl_calib_indicator.setText(""))

    @Slot(list)
    def handle_new_frame(self, frame_data):
        self.packet_count += 1
        self.fps_packet_count += 1

        if len(frame_data) < 40:
            frame_data = frame_data + [0.0] * (40 - len(frame_data))
        elif len(frame_data) > 40:
            frame_data = frame_data[:40]

        frame = np.array(frame_data, dtype=float)

        self.raw_history[:, :-1] = self.raw_history[:, 1:]
        self.raw_history[:, -1] = frame

        if self.is_calibrating:
            self.calibration_buffer.append(frame)
            if len(self.calibration_buffer) >= 50:
                self.finish_calibration()

        if self.baseline is not None:
            calibrated_frame = np.maximum(0, frame - self.baseline)
            self.calibrated_history[:, :-1] = self.calibrated_history[:, 1:]
            self.calibrated_history[:, -1] = calibrated_frame

    def calculate_data_rate(self):
        now = datetime.now()
        dt = (now - self.last_fps_time).total_seconds()
        if dt > 0:
            self.current_freq_hz = self.fps_packet_count / dt
        self.fps_packet_count = 0
        self.last_fps_time = now

    def refresh_ui_elements(self):
        self.lbl_hz.setText(f"Data Rate: {self.current_freq_hz:.1f} Hz")
        self.lbl_packets.setText(f"Packets Rx: {self.packet_count}")

        # Update Heatmap
        if self.rb_mode_live.isChecked():
            active_buf = self.calibrated_history if self.baseline is not None else self.raw_history
            latest_frame = active_buf[:, -1].tolist()
            self.heatmap.update_data(latest_frame, max_val=self.current_max_scale)

        # Update Live Settling Waveform Plot for Active Channel
        target_buf = self.calibrated_history if self.baseline is not None else self.raw_history
        target_signal = target_buf[self.selected_channel, :]
        self.time_curve.setData(target_signal)
        cur_val = target_signal[-1]
        self.plot_time.setTitle(f"Channel {self.selected_channel:02d} Live Signal Trace (Current Value: {cur_val:.1f} ADC counts)")

    def closeEvent(self, event):
        self.conn.stop()
        event.accept()

    def apply_dark_theme(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #121212;
            }
            QWidget {
                color: #e0e0e0;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                font-size: 12px;
            }
            #HeaderCard {
                background-color: #1a1a1a;
                border: 1px solid #282828;
                border-radius: 8px;
            }
            #StatusDisconnected {
                background-color: #ff3333;
                color: #ffffff;
                font-weight: bold;
                border-radius: 4px;
            }
            QGroupBox {
                border: 1px solid #282828;
                border-radius: 8px;
                margin-top: 15px;
                font-weight: bold;
                font-size: 11px;
                color: #00ff9d;
                text-transform: uppercase;
                background-color: #161616;
                padding: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 10px;
                padding: 0 5px;
                background-color: #121212;
            }
            QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {
                background-color: #222;
                border: 1px solid #333;
                border-radius: 4px;
                padding: 4px 8px;
                color: #fff;
                font-family: monospace;
                min-height: 20px;
            }
            QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {
                color: #666;
                background-color: #151515;
            }
            QPushButton {
                background-color: #222;
                border: 1px solid #333;
                border-radius: 4px;
                color: #fff;
                padding: 6px 12px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #2d2d2d;
                border-color: #444;
            }
            QPushButton:pressed {
                background-color: #181818;
            }
            #BtnConnect {
                background-color: #0088ff;
                color: #fff;
                font-weight: bold;
            }
            #BtnCalibrate {
                background-color: #ffaa00;
                color: #111;
                font-weight: bold;
            }
            #BtnCalibrate:disabled {
                background-color: #333;
                color: #666;
            }
            QRadioButton {
                color: #aaa;
                font-weight: bold;
                spacing: 6px;
            }
            QRadioButton:checked {
                color: #00ff9d;
            }
            QSplitter::handle {
                background-color: #222;
            }
        """)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MatSensitivityTesterApp()
    window.show()
    sys.exit(app.exec())
