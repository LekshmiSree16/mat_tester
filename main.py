from PySide6.QtWidgets import QGridLayout
import sys
import os
import csv
from datetime import datetime
import numpy as np

from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QComboBox, QPushButton, QLabel, QGroupBox, QProgressBar,
                               QCheckBox, QSpinBox, QTextEdit, QLineEdit, QScrollArea, QSplitter, QFrame, QTabWidget)
from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QFont, QTextCursor

import pyqtgraph as pg

# Local imports
from connection_manager import IsolatedConnectionManager
from pressure_map import PressureHeatmapWidget
from breathing_waveform import BreathingWaveformWidget


class MatTesterApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Luxisens Optical Fiber Mat Tester & Analyzer")
        self.resize(1450, 950)

        # 1. State Variables
        self.conn = IsolatedConnectionManager()
        self.conn.new_frame_signal.connect(self.handle_new_frame)
        self.conn.connection_status_signal.connect(self.handle_connection_status)
        self.conn.at_command_received_signal.connect(self.handle_at_command_received)
        self.conn.at_command_sent_signal.connect(self.handle_at_command_sent)
        self.conn.new_rwav_signal.connect(self.handle_new_rwav)
        self.conn.new_rr_value_signal.connect(self.handle_new_rr_value)

        # Buffer limits
        self.history_size = 500  # 10 seconds at 50Hz
        
        # Sensor data arrays
        self.raw_history = np.zeros((40, self.history_size))
        self.calibrated_history = np.zeros((40, self.history_size))
        self.time_index = 0
        self.selected_channel = 11  # Default to channel 11
        self.current_max_scale = 32000
        
        # Calibration state
        self.is_calibrating = False
        self.calibration_buffer = []
        self.baseline = None  # None means no calibration baseline applied

        # CSV Logging state
        self.is_logging = False
        self.log_file = None
        self.log_writer = None
        self.log_count = 0

        # Performance metric tracking
        self.packet_count = 0
        self.fps_packet_count = 0
        self.last_fps_time = datetime.now()
        self.current_freq_hz = 0.0

        # 2. Setup the User Interface
        self.setup_ui()
        self.populate_serial_ports()

        # Connect theme styles
        self.apply_dark_theme()

        # 3. Decoupled Visual Refresh Timer
        self.ui_timer = QTimer(self)
        self.ui_timer.timeout.connect(self.refresh_ui_elements)
        self.ui_timer.start(50)  # 20 FPS UI refresh

        # Slow 1-second timer for connection data rate
        self.sec_timer = QTimer(self)
        self.sec_timer.timeout.connect(self.calculate_data_rate)
        self.sec_timer.start(1000)

    def populate_serial_ports(self):
        self.cb_ports.clear()
        ports = self.conn.get_ports()
        if ports:
            self.cb_ports.addItems(ports)
            # Auto-select STM32 if we can spot it (PID 3752/374B or containing STM)
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
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # ==========================================
        # 1. HEADER SECTION (Connection metrics)
        # ==========================================
        header_widget = QFrame()
        header_widget.setObjectName("HeaderCard")
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(15, 10, 15, 10)

        title_lbl = QLabel("LUXISENS OPTICAL FIBER MAT TESTER")
        title_lbl.setStyleSheet("font-size: 20px; font-weight: bold; color: #00ff9d; letter-spacing: 1px;")
        
        self.lbl_conn_status = QLabel("DISCONNECTED")
        self.lbl_conn_status.setObjectName("StatusDisconnected")
        self.lbl_conn_status.setAlignment(Qt.AlignCenter)
        self.lbl_conn_status.setFixedWidth(200)

        self.lbl_hz = QLabel("Data Rate: 0.0 Hz")
        self.lbl_hz.setStyleSheet("font-size: 14px; color: #aaa; font-family: monospace;")
        
        self.lbl_packets = QLabel("Packets Rx: 0")
        self.lbl_packets.setStyleSheet("font-size: 14px; color: #aaa; font-family: monospace;")

        header_layout.addWidget(title_lbl)
        header_layout.addStretch()
        header_layout.addWidget(self.lbl_hz)
        header_layout.addWidget(self.lbl_packets)
        header_layout.addWidget(self.lbl_conn_status)
        main_layout.addWidget(header_widget)

        # ==========================================
        # 2. MAIN BODY (Splitter Layout)
        # ==========================================
        body_splitter = QSplitter(Qt.Horizontal)
        
        # ------------------------------------------
        # LEFT COLUMN: Connection & Commands Console
        # ------------------------------------------
        left_col = QWidget()
        left_layout = QVBoxLayout(left_col)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        # Group A: Connection Controls
        conn_group = QGroupBox("Hardware Interface Settings")
        conn_layout = QVBoxLayout(conn_group)
        conn_layout.setSpacing(8)
        
        # Radio / Dropdown select for Mode
        mode_layout = QHBoxLayout()
        lbl_mode = QLabel("Interface Source:")
        lbl_mode.setFixedWidth(140)
        self.cb_mode = QComboBox()
        self.cb_mode.addItems(["Serial (COM Port)", "Wi-Fi (DataGram-6060)", "Live Simulator"])
        self.cb_mode.currentIndexChanged.connect(self.on_mode_changed)
        mode_layout.addWidget(lbl_mode)
        mode_layout.addWidget(self.cb_mode, 1)
        conn_layout.addLayout(mode_layout)

        # Serial Specific Settings Container
        self.serial_settings_widget = QWidget()
        self.serial_settings_widget.setObjectName("SerialSettingsWidget")
        serial_lay = QVBoxLayout(self.serial_settings_widget)
        serial_lay.setContentsMargins(0, 0, 0, 0)
        serial_lay.setSpacing(8)
        
        port_lay = QHBoxLayout()
        lbl_port = QLabel("COM Port:")
        lbl_port.setFixedWidth(140)
        self.cb_ports = QComboBox()
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setFixedWidth(65)
        self.btn_refresh.setFixedHeight(24)
        self.btn_refresh.clicked.connect(self.populate_serial_ports)
        port_lay.addWidget(lbl_port)
        port_lay.addWidget(self.cb_ports, 1)
        port_lay.addWidget(self.btn_refresh)
        serial_lay.addLayout(port_lay)

        baud_lay = QHBoxLayout()
        lbl_baud = QLabel("Baud Rate:")
        lbl_baud.setFixedWidth(140)
        self.cb_baud = QComboBox()
        self.cb_baud.addItems(["921600", "460800", "115200", "9600"])
        baud_lay.addWidget(lbl_baud)
        baud_lay.addWidget(self.cb_baud, 1)
        serial_lay.addLayout(baud_lay)
        conn_layout.addWidget(self.serial_settings_widget)

        # UDP Specific Settings Container
        self.udp_settings_widget = QWidget()
        self.udp_settings_widget.setVisible(False)
        udp_lay = QHBoxLayout(self.udp_settings_widget)
        udp_lay.setContentsMargins(0, 0, 0, 0)
        udp_lay.setSpacing(8)
        lbl_udp = QLabel("DataGram Port:")
        lbl_udp.setFixedWidth(140)
        self.txt_udp_port = QLineEdit("6060")
        udp_lay.addWidget(lbl_udp)
        udp_lay.addWidget(self.txt_udp_port, 1)
        conn_layout.addWidget(self.udp_settings_widget)

        # Hardware Mat Light Sensitivity Setting (INTT)
        sens_lay = QHBoxLayout()
        lbl_sens = QLabel("Mat Light Sensitivity (INTT):")
        lbl_sens.setFixedWidth(140)
        self.cb_sens_hw = QComboBox()
        self.cb_sens_hw.addItems(["50", "100", "500", "1000", "1500", "2000", "3000"])
        self.cb_sens_hw.setCurrentIndex(2) # Default to 500
        self.cb_sens_hw.currentIndexChanged.connect(self.on_hw_sensitivity_changed)
        sens_lay.addWidget(lbl_sens)
        sens_lay.addWidget(self.cb_sens_hw, 1)
        conn_layout.addLayout(sens_lay)

        # Buttons
        btn_lay = QHBoxLayout()
        btn_lay.setSpacing(10)
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

        # Group B: AT Command Console
        console_group = QGroupBox("Mat Command Console (STM32 AT commands)")
        console_layout = QVBoxLayout(console_group)

        self.txt_console = QTextEdit()
        self.txt_console.setReadOnly(True)
        self.txt_console.setFont(QFont("Courier New", 9))
        self.txt_console.setStyleSheet("background-color: #0b0b0b; border: 1px solid #333; color: #fff;")
        console_layout.addWidget(self.txt_console)

        # Quick Commands buttons grid
        quick_layout = QHBoxLayout()
        self.btn_cmd_ver = QPushButton("Query Version")
        self.btn_cmd_ver.clicked.connect(lambda: self.send_console_command("AT+VER"))
        self.btn_cmd_neonat = QPushButton("Set NeoNat")
        self.btn_cmd_neonat.clicked.connect(lambda: self.send_console_command("AT+MATMOD NeoNat"))
        self.btn_cmd_adult = QPushButton("Set Adult")
        self.btn_cmd_adult.clicked.connect(lambda: self.send_console_command("AT+MATMOD Adult"))
        
        quick_layout.addWidget(self.btn_cmd_ver)
        quick_layout.addWidget(self.btn_cmd_neonat)
        quick_layout.addWidget(self.btn_cmd_adult)
        console_layout.addLayout(quick_layout)

        # Custom line input
        input_layout = QHBoxLayout()
        input_layout.setSpacing(8)
        self.txt_cmd_input = QLineEdit()
        self.txt_cmd_input.setFixedHeight(26)
        self.txt_cmd_input.setPlaceholderText("Enter custom AT command (e.g. AT+STAT)...")
        self.txt_cmd_input.returnPressed.connect(self.send_custom_cmd)
        
        self.btn_send_cmd = QPushButton("Send")
        self.btn_send_cmd.setFixedWidth(65)
        self.btn_send_cmd.setFixedHeight(26)
        self.btn_send_cmd.clicked.connect(self.send_custom_cmd)
        
        input_layout.addWidget(self.txt_cmd_input, 1)
        input_layout.addWidget(self.btn_send_cmd)
        console_layout.addLayout(input_layout)

        left_layout.addWidget(console_group, 1)
        
        # Wrap left column in a scroll area and limit its width to make it slightly smaller
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setStyleSheet("QScrollArea { background-color: transparent; border: none; }")
        left_scroll.setWidget(left_col)
        left_scroll.setMaximumWidth(350)
        body_splitter.addWidget(left_scroll)

        # ------------------------------------------
        # MIDDLE COLUMN: Spatial Heatmap & Channel Progress Bars
        # ------------------------------------------
        mid_col = QWidget()
        mid_layout = QVBoxLayout(mid_col)
        mid_layout.setContentsMargins(0, 0, 0, 0)
        mid_layout.setSpacing(10)

        # Double Heatmap container for comparing linear and swapped layouts side-by-side
        heat_container = QWidget()
        heat_lay = QHBoxLayout(heat_container)
        heat_lay.setContentsMargins(0, 0, 0, 0)
        heat_lay.setSpacing(10)

        # 1. Linear Heatmap (Unswapped Raw Channels)
        self.heatmap_linear = PressureHeatmapWidget("Linear Raw Map (Unswapped)", use_swapped_layout=False, cell_size=50)
        self.heatmap_linear.sensor_selected.connect(self.change_selected_channel)
        heat_lay.addWidget(self.heatmap_linear)

        # 2. Patient Monitor Swapped Heatmap (Matches Bedside Monitor display correction)
        self.heatmap = PressureHeatmapWidget("Patient Monitor Map (Swapped)", use_swapped_layout=True, cell_size=50, is_patient_monitor_style=True)
        self.heatmap.sensor_selected.connect(self.change_selected_channel)
        heat_lay.addWidget(self.heatmap)

        mid_layout.addWidget(heat_container, 0, Qt.AlignCenter)

        # Channel progress bar viewer (scrollable side-by-side layout)
        bar_group = QGroupBox("All 40 Optical Channels Diagnostics")
        bar_group.setFixedWidth(562) # Aligned with double heatmap container width
        bar_layout = QVBoxLayout(bar_group)
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("background-color: #1a1a1a; border: none;")
        
        scroll_widget = QWidget()
        scroll_main_layout = QHBoxLayout(scroll_widget)
        scroll_main_layout.setContentsMargins(5, 5, 5, 5)
        scroll_main_layout.setSpacing(15)

        # Left Column (Ch 00 - 19)
        left_col_widget = QWidget()
        left_col_lay = QVBoxLayout(left_col_widget)
        left_col_lay.setContentsMargins(0, 0, 0, 0)
        left_col_lay.setSpacing(4)

        # Right Column (Ch 20 - 39)
        right_col_widget = QWidget()
        right_col_lay = QVBoxLayout(right_col_widget)
        right_col_lay.setContentsMargins(0, 0, 0, 0)
        right_col_lay.setSpacing(4)

        self.channel_bars = []
        for i in range(40):
            row_w = QWidget()
            row_lay = QHBoxLayout(row_w)
            row_lay.setContentsMargins(3, 3, 3, 3)
            row_lay.setSpacing(6)

            lbl = QLabel(f"Ch {i:02d}:")
            lbl.setFixedWidth(50)
            lbl.setStyleSheet("color: #bbb; font-family: monospace; font-size: 12px; font-weight: bold;")
            
            bar = QProgressBar()
            bar.setRange(0, self.current_max_scale)
            bar.setValue(0)
            bar.setTextVisible(False)
            bar.setFixedHeight(20)  # Taller progress bars (from 12px to 20px)
            bar.setStyleSheet("""
                QProgressBar { 
                    border: 1px solid #333; 
                    border-radius: 4px; 
                    background-color: #111; 
                } 
                QProgressBar::chunk { 
                    background-color: #0088ff; 
                    border-radius: 3px;
                }
            """)

            lbl_val = QLabel("0")
            lbl_val.setFixedWidth(45)
            lbl_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            lbl_val.setStyleSheet("color: #00ff9d; font-family: monospace; font-size: 12px; font-weight: bold;")

            row_lay.addWidget(lbl)
            row_lay.addWidget(bar, 1)
            row_lay.addWidget(lbl_val)
            
            if i < 20:
                left_col_lay.addWidget(row_w)
            else:
                right_col_lay.addWidget(row_w)
                
            self.channel_bars.append((bar, lbl_val, row_w))

        left_col_lay.addStretch()
        right_col_lay.addStretch()

        scroll_main_layout.addWidget(left_col_widget, 1)
        scroll_main_layout.addWidget(right_col_widget, 1)

        scroll_area.setWidget(scroll_widget)
        bar_layout.addWidget(scroll_area)
        mid_layout.addWidget(bar_group, 1, Qt.AlignCenter)
        
        # Wrap middle column in a scroll area and set its minimum width to accommodate the heatmaps
        mid_scroll = QScrollArea()
        mid_scroll.setWidgetResizable(True)
        mid_scroll.setStyleSheet("QScrollArea { background-color: transparent; border: none; }")
        mid_scroll.setWidget(mid_col)
        mid_scroll.setMinimumWidth(580)
        body_splitter.addWidget(mid_scroll)

        # ------------------------------------------
        # RIGHT COLUMN: Plots & Statistics
        # ------------------------------------------
        right_col = QWidget()
        right_layout = QVBoxLayout(right_col)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        # Graph selection & CSV group
        plot_ctrl_group = QGroupBox("Selected Channel Controls & Logger")
        plot_ctrl_layout = QGridLayout(plot_ctrl_group)
        plot_ctrl_layout.setContentsMargins(10, 10, 10, 10)
        plot_ctrl_layout.setHorizontalSpacing(8)
        plot_ctrl_layout.setVerticalSpacing(8)
        
        # Row 0: Active Channel Plot
        lbl_act = QLabel("Active Channel Plot:")
        lbl_act.setFixedWidth(135)
        lbl_act.setStyleSheet("color: #aaa; font-weight: bold; font-size: 11px;")
        
        self.sp_channel = QSpinBox()
        self.sp_channel.setRange(0, 39)
        self.sp_channel.setValue(self.selected_channel)
        self.sp_channel.valueChanged.connect(self.change_selected_channel)
        self.sp_channel.setFixedWidth(60)
        
        self.cb_graph_source = QComboBox()
        self.cb_graph_source.addItems(["Selected Channel", "Average of All Channels", "Max Value Channel", "Noisiest Channel"])
        self.cb_graph_source.currentIndexChanged.connect(self.on_graph_source_changed)
        
        plot_ctrl_layout.addWidget(lbl_act, 0, 0, Qt.AlignLeft | Qt.AlignVCenter)
        plot_ctrl_layout.addWidget(self.sp_channel, 0, 1, Qt.AlignLeft | Qt.AlignVCenter)
        plot_ctrl_layout.addWidget(self.cb_graph_source, 0, 2)

        # Row 1: Visualization Sensitivity
        lbl_vis = QLabel("Visualization Sensitivity:")
        lbl_vis.setFixedWidth(135)
        lbl_vis.setStyleSheet("color: #aaa; font-weight: bold; font-size: 11px;")
        
        self.cb_vis_sensitivity = QComboBox()
        self.cb_vis_sensitivity.addItems([
            "High (0 - 2,000)", 
            "Medium-High (0 - 4,000)", 
            "Medium (0 - 8,000)", 
            "Medium-Low (0 - 16,000)", 
            "Low (0 - 32,000) (Default)"
        ])
        self.cb_vis_sensitivity.setCurrentIndex(4) # Default Low
        self.cb_vis_sensitivity.currentIndexChanged.connect(self.on_vis_sensitivity_changed)
        
        plot_ctrl_layout.addWidget(lbl_vis, 1, 0, Qt.AlignLeft | Qt.AlignVCenter)
        plot_ctrl_layout.addWidget(self.cb_vis_sensitivity, 1, 1, 1, 2)

        # Row 2: CSV Log Name
        lbl_csv = QLabel("CSV Log Name:")
        lbl_csv.setFixedWidth(135)
        lbl_csv.setStyleSheet("color: #aaa; font-weight: bold; font-size: 11px;")
        
        self.txt_csv_prefix = QLineEdit("MatTestLog")
        self.txt_csv_prefix.setPlaceholderText("File prefix")
        self.txt_csv_prefix.setFixedHeight(24)
        
        self.btn_csv_record = QPushButton("START LOGGING")
        self.btn_csv_record.setObjectName("BtnCsvRecord")
        self.btn_csv_record.setFixedHeight(24)
        self.btn_csv_record.clicked.connect(self.toggle_csv_logging)
        
        plot_ctrl_layout.addWidget(lbl_csv, 2, 0, Qt.AlignLeft | Qt.AlignVCenter)
        plot_ctrl_layout.addWidget(self.txt_csv_prefix, 2, 1)
        plot_ctrl_layout.addWidget(self.btn_csv_record, 2, 2)

        # Row 3: Logger status
        self.lbl_csv_status = QLabel("Logger Idle")
        self.lbl_csv_status.setStyleSheet("color: #888; font-family: monospace; font-size: 11px;")
        plot_ctrl_layout.addWidget(self.lbl_csv_status, 3, 1, 1, 2)

        right_layout.addWidget(plot_ctrl_group)

        # Stat cards grid
        stats_group = QGroupBox("Real-Time Analytics Dashboard")
        stats_layout = QGridLayout(stats_group)
        stats_layout.setSpacing(10)

        self.stat_min = self.create_stat_card("Minimum Value", "0")
        self.stat_max = self.create_stat_card("Maximum Value", "0")
        self.stat_avg = self.create_stat_card("Average Intensity", "0")
        self.stat_p2p = self.create_stat_card("Peak-to-Peak Var", "0")
        self.stat_snr = self.create_stat_card("Est. SNR", "0.0")

        stats_layout.addWidget(self.stat_min, 0, 0)
        stats_layout.addWidget(self.stat_max, 0, 1)
        stats_layout.addWidget(self.stat_avg, 0, 2)
        stats_layout.addWidget(self.stat_p2p, 1, 0)
        stats_layout.addWidget(self.stat_snr, 1, 1)
        
        # Info card in empty slot
        info_card = QFrame()
        info_card.setStyleSheet("background-color: #222; border: 1px solid #333; border-radius: 6px; padding: 5px;")
        info_lay = QVBoxLayout(info_card)
        info_lay.setContentsMargins(5, 5, 5, 5)
        lbl_info = QLabel("Max Limit: 32768 (15-bit ADC)\nNormal Respiration P2P: 500-2000\nNoisy/EMI Zone: Var > 4000")
        lbl_info.setStyleSheet("color: #bbb; font-size: 9px; font-family: monospace;")
        info_lay.addWidget(lbl_info)
        stats_layout.addWidget(info_card, 1, 2)

        right_layout.addWidget(stats_group)

        # Respiration Wave Panel (Bedside Monitor style)
        resp_panel_group = QGroupBox("Live Respiration Monitor (Patient Monitor Wave & Value)")
        resp_panel_layout = QHBoxLayout(resp_panel_group)
        resp_panel_layout.setContentsMargins(10, 8, 10, 8)
        resp_panel_layout.setSpacing(15)

        # Scrolling Breathing wave
        self.wave_widget = BreathingWaveformWidget()
        self.wave_widget.setMinimumHeight(130)
        resp_panel_layout.addWidget(self.wave_widget, 4)

        # Numeric display area on the right
        rr_display_layout = QVBoxLayout()
        rr_display_layout.setAlignment(Qt.AlignCenter)
        rr_display_layout.setSpacing(2)
        
        rr_lbl_title = QLabel("RR (BPM)")
        rr_lbl_title.setStyleSheet("color: #00d4ff; font-weight: bold; font-size: 11px; text-transform: uppercase;")
        rr_lbl_title.setAlignment(Qt.AlignCenter)
        
        self.lbl_rr_val = QLabel("--")
        self.lbl_rr_val.setStyleSheet("color: #00d4ff; font-size: 56px; font-weight: bold; font-family: monospace;")
        self.lbl_rr_val.setAlignment(Qt.AlignCenter)
        
        rr_display_layout.addWidget(rr_lbl_title)
        rr_display_layout.addWidget(self.lbl_rr_val)
        resp_panel_layout.addLayout(rr_display_layout, 1)

        right_layout.addWidget(resp_panel_group)

        # Tab layout for secondary plots
        self.analysis_tabs = QTabWidget()
        self.analysis_tabs.setMinimumHeight(350)
        self.analysis_tabs.setStyleSheet("""
            QTabWidget::panel {
                border: 1px solid #2d2d2d;
                background-color: #151515;
                border-radius: 4px;
            }
            QTabBar::tab {
                background-color: #222;
                color: #aaa;
                border: 1px solid #2d2d2d;
                border-bottom: none;
                padding: 6px 12px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-weight: bold;
                font-size: 11px;
            }
            QTabBar::tab:selected {
                background-color: #151515;
                color: #00ff9d;
                border-bottom: 2px solid #00ff9d;
            }
        """)

        # Tab 1: Raw Channel Plot
        tab_raw = QWidget()
        lay_raw = QVBoxLayout(tab_raw)
        lay_raw.setContentsMargins(5, 5, 5, 5)
        
        pg.setConfigOption('background', '#151515')
        pg.setConfigOption('foreground', '#d0d0d0')

        self.plot_time = pg.PlotWidget(title="RAW CHANNEL WAVEFORM OVER TIME (Respiration Trace)")
        self.plot_time.setLabel('left', 'Optical Signal')
        self.plot_time.setLabel('bottom', 'Samples (Last 10 Seconds)')
        self.plot_time.showGrid(x=True, y=True, alpha=0.3)
        self.time_curve = self.plot_time.plot(pen=pg.mkPen(color='#ff007f', width=2))
        lay_raw.addWidget(self.plot_time)

        # Tab 2: FFT Noise Spectrum
        tab_fft = QWidget()
        lay_fft = QVBoxLayout(tab_fft)
        lay_fft.setContentsMargins(5, 5, 5, 5)

        self.plot_fft = pg.PlotWidget(title="FFT SPECTRUM (Electrical/Mechanical Noise Analysis)")
        self.plot_fft.setLabel('left', 'Magnitude')
        self.plot_fft.setLabel('bottom', 'Frequency (Hz)')
        self.plot_fft.showGrid(x=True, y=True, alpha=0.3)
        self.plot_fft.setXRange(0, 25)
        self.fft_curve = self.plot_fft.plot(pen=pg.mkPen(color='#00ff9d', width=2))
        lay_fft.addWidget(self.plot_fft)

        self.analysis_tabs.addTab(tab_raw, "Raw Waveform Tracker")
        self.analysis_tabs.addTab(tab_fft, "FFT Interference Spectrum")

        right_layout.addWidget(self.analysis_tabs, 1)

        # Wrap right column in a scroll area to prevent any height overflow clipping
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setStyleSheet("QScrollArea { background-color: transparent; border: none; }")
        right_scroll.setWidget(right_col)
        body_splitter.addWidget(right_scroll)

        # Final layout adjustments with hover-adjustable splitter
        body_splitter.setStretchFactor(0, 0) # left
        body_splitter.setStretchFactor(1, 0) # middle
        body_splitter.setStretchFactor(2, 1) # right (give graphs more width)
        main_layout.addWidget(body_splitter, 1)

    def create_stat_card(self, title, val):
        card = QFrame()
        card.setStyleSheet("background-color: #222; border: 1px solid #333; border-radius: 6px; padding: 5px;")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(5, 5, 5, 5)
        lay.setSpacing(2)
        
        t_lbl = QLabel(title)
        t_lbl.setStyleSheet("color: #888; font-size: 10px; font-weight: bold; text-transform: uppercase;")
        v_lbl = QLabel(val)
        v_lbl.setStyleSheet("color: #00ff9d; font-size: 18px; font-family: monospace; font-weight: bold;")
        
        lay.addWidget(t_lbl)
        lay.addWidget(v_lbl)
        
        # Tag the value label so we can update it
        card.value_label = v_lbl
        return card

    # ==========================================
    # EVENT HANDLERS / CALLBACKS
    # ==========================================

    def on_mode_changed(self, idx):
        is_serial = (idx == 0)
        is_udp = (idx == 1)
        
        self.serial_settings_widget.setVisible(is_serial)
        self.udp_settings_widget.setVisible(is_udp)

    def on_graph_source_changed(self, idx):
        # Enable or disable the spinbox depending on source
        # "Selected Channel" is index 0
        self.sp_channel.setEnabled(idx == 0)

    @Slot(int)
    def on_vis_sensitivity_changed(self, index):
        scales = [2000, 4000, 8000, 16000, 32000]
        self.current_max_scale = scales[index]
        
        # Update progress bar ranges dynamically
        for bar, _, _ in self.channel_bars:
            bar.setRange(0, self.current_max_scale)

    @Slot(int)
    def on_hw_sensitivity_changed(self, index):
        val = self.cb_sens_hw.currentText()
        if self.conn.running:
            self.conn.send_command(f"AT+INTT {val}")
        else:
            self.txt_console.append(f"<span style='color:yellow;'>System: Sensitivity set to {val} (will apply on connect)</span>")

    @Slot(int)
    def change_selected_channel(self, val):
        """Triggered when spinner or heatmap cell clicked changes"""
        if self.selected_channel == val:
            return
        self.selected_channel = val
        self.sp_channel.blockSignals(True)
        self.sp_channel.setValue(val)
        self.sp_channel.blockSignals(False)
        
        # Update selected border in both heatmaps
        self.heatmap.blockSignals(True)
        self.heatmap.select_sensor_programmatically(val)
        self.heatmap.blockSignals(False)

        self.heatmap_linear.blockSignals(True)
        self.heatmap_linear.select_sensor_programmatically(val)
        self.heatmap_linear.blockSignals(False)

        # Visual highlights in channel bargraph
        for i, (bar, lbl_val, row_w) in enumerate(self.channel_bars):
            if i == val:
                row_w.setStyleSheet("background-color: #2b2b2b; border-radius: 4px; border: 1px solid #555;")
                bar.setStyleSheet("""
                    QProgressBar { 
                        border: 1px solid #00ff9d; 
                        border-radius: 4px; 
                        background-color: #111; 
                    } 
                    QProgressBar::chunk { 
                        background-color: #00ff9d; 
                        border-radius: 3px;
                    }
                """)
            else:
                row_w.setStyleSheet("")
                bar.setStyleSheet("""
                    QProgressBar { 
                        border: 1px solid #333; 
                        border-radius: 4px; 
                        background-color: #111; 
                    } 
                    QProgressBar::chunk { 
                        background-color: #0088ff; 
                        border-radius: 3px;
                    }
                """)

    def toggle_connection(self):
        if self.conn.running:
            self.conn.stop()
            self.btn_calibrate.setEnabled(False)
        else:
            mode_idx = self.cb_mode.currentIndex()
            success = False
            
            if mode_idx == 0:
                # Serial
                port_str = self.cb_ports.currentText()
                if "COM" not in port_str and "tty" not in port_str:
                    self.txt_console.append("<span style='color:red;'>System: Select a valid port first!</span>")
                    return
                clean_port = port_str.split(" - ")[0]
                baud = int(self.cb_baud.currentText())
                success = self.conn.start_serial(clean_port, baud)
            elif mode_idx == 1:
                # UDP
                try:
                    port = int(self.txt_udp_port.text())
                    success = self.conn.start_udp(port)
                except ValueError:
                    self.txt_console.append("<span style='color:red;'>System: Invalid UDP Port!</span>")
                    return
            else:
                # Simulator
                success = self.conn.start_simulator()

            if success:
                self.btn_calibrate.setEnabled(True)

    def start_calibration(self):
        """Zeros the sensor values by recording a 50-frame baseline"""
        if not self.conn.running:
            return
            
        self.is_calibrating = True
        self.calibration_buffer = []
        self.btn_calibrate.setEnabled(False)
        self.lbl_calib_indicator.setText("ZEROING MAT: RECORDING STILL BASELINE...")

    def toggle_csv_logging(self):
        if self.is_logging:
            # Stop Logging
            self.is_logging = False
            self.btn_csv_record.setText("START LOGGING")
            self.btn_csv_record.setStyleSheet("")
            if self.log_file:
                self.log_file.close()
                self.log_file = None
            self.lbl_csv_status.setText(f"Stopped. Saved {self.log_count} samples.")
        else:
            # Start Logging
            prefix = self.txt_csv_prefix.text().strip()
            if not prefix:
                prefix = "MatTest"
            
            os.makedirs("mat_logs", exist_ok=True)
            filename = f"mat_logs/{prefix}_{datetime.now().strftime('%Y%d%H_%H%M%S')}.csv"
            
            try:
                self.log_file = open(filename, 'w', newline='')
                self.log_writer = csv.writer(self.log_file)
                
                # Header
                headers = ["Timestamp", "SelectedChannel", "ActiveSource"] + [f"Ch{i}" for i in range(40)]
                self.log_writer.writerow(headers)
                
                self.is_logging = True
                self.log_count = 0
                self.btn_csv_record.setText("STOP LOGGING")
                self.btn_csv_record.setStyleSheet("background-color: #ff3333; color: white;")
                self.lbl_csv_status.setText(f"Recording to: {filename}")
            except Exception as e:
                self.lbl_csv_status.setText(f"Log Error: {e}")

    def send_custom_cmd(self):
        cmd = self.txt_cmd_input.text().strip()
        if cmd:
            self.send_console_command(cmd)
            self.txt_cmd_input.clear()

    def send_console_command(self, cmd):
        if self.conn.running:
            self.conn.send_command(cmd)
        else:
            self.txt_console.append(f"<span style='color:red;'>System: Connect to send command '{cmd}'</span>")

    # ==========================================
    # DATA INTAKE & SIGNAL PACKAGES
    # ==========================================

    @Slot(list)
    def handle_new_frame(self, frame_data):
        """Invoked at 50Hz. Thread-safe execution."""
        # Check matching dimension (pad or slice to exactly 40 values)
        if len(frame_data) < 40:
            # Pad
            frame_data = frame_data + [0] * (40 - len(frame_data))
        elif len(frame_data) > 40:
            # Slice
            frame_data = frame_data[:40]

        # 1. Check calibration baseline routine
        if self.is_calibrating:
            self.calibration_buffer.append(frame_data)
            pct = int((len(self.calibration_buffer) / 50.0) * 100)
            self.lbl_calib_indicator.setText(f"ZERO CALIBRATING MAT... {pct}%")
            
            if len(self.calibration_buffer) >= 50:
                self.baseline = np.mean(self.calibration_buffer, axis=0)
                self.is_calibrating = False
                self.btn_calibrate.setEnabled(True)
                self.lbl_calib_indicator.setText("ZERO COMPLETED (Baseline Applied)")
                QTimer.singleShot(4000, lambda: self.lbl_calib_indicator.setText("Calibration: Applied"))
            return

        # 2. Subtract baseline if calibrated
        raw_arr = np.array(frame_data)
        if self.baseline is not None:
            processed_arr = np.clip(raw_arr - self.baseline, 0, None)
        else:
            processed_arr = raw_arr

        # 3. Store to rolling history buffers
        self.raw_history[:, :-1] = self.raw_history[:, 1:]
        self.raw_history[:, -1] = raw_arr

        self.calibrated_history[:, :-1] = self.calibrated_history[:, 1:]
        self.calibrated_history[:, -1] = processed_arr

        # Increment packet metrics
        self.packet_count += 1
        self.fps_packet_count += 1

        # 4. Write to CSV log if active
        if self.is_logging and self.log_writer:
            try:
                stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                row = [stamp, self.selected_channel, self.conn.mode] + raw_arr.tolist()
                self.log_writer.writerow(row)
                self.log_count += 1
                if self.log_count % 50 == 0:
                    self.lbl_csv_status.setText(f"Logging... Recorded {self.log_count} frames.")
            except Exception as e:
                self.is_logging = False
                self.lbl_csv_status.setText(f"Write failure: {e}")

    @Slot(str, bool)
    def handle_connection_status(self, msg, connected):
        self.btn_connect.setText("DISCONNECT" if connected else "CONNECT")
        if connected:
            self.lbl_conn_status.setText("ACTIVE")
            self.lbl_conn_status.setStyleSheet("background-color: #00ff9d; color: #111; font-weight: bold; border-radius: 4px;")
            self.txt_console.append(f"<span style='color:#00ff9d;'>System: {msg}</span>")
            # Automatically sync mat light sensitivity (INTT) shortly after boot/connection
            QTimer.singleShot(4000 if self.cb_mode.currentIndex() == 0 else 500, 
                               lambda: self.conn.send_command(f"AT+INTT {self.cb_sens_hw.currentText()}"))
        else:
            self.lbl_conn_status.setText("DISCONNECTED")
            self.lbl_conn_status.setStyleSheet("background-color: #ff3333; color: #fff; font-weight: bold; border-radius: 4px;")
            self.txt_console.append(f"<span style='color:red;'>System: {msg}</span>")
            self.btn_calibrate.setEnabled(False)
            if hasattr(self, 'wave_widget'):
                self.wave_widget.clear()
            if hasattr(self, 'lbl_rr_val'):
                self.lbl_rr_val.setText("--")

    @Slot(float)
    def handle_new_rwav(self, val):
        if hasattr(self, 'wave_widget'):
            self.wave_widget.push_sample(val)

    @Slot(int)
    def handle_new_rr_value(self, val):
        if hasattr(self, 'lbl_rr_val'):
            self.lbl_rr_val.setText(str(val))

    @Slot(str)
    def handle_at_command_received(self, line):
        self.txt_console.append(f"<span style='color:#ffffff;'>[RX] &lt; {line}</span>")
        # Scroll console to bottom
        self.txt_console.moveCursor(QTextCursor.End)

    @Slot(str)
    def handle_at_command_sent(self, line):
        self.txt_console.append(f"<span style='color:#00ff9d;'>[TX] &gt; {line}</span>")
        self.txt_console.moveCursor(QTextCursor.End)

    # ==========================================
    # TIMED METRIC CALCULATORS & UI UPDATERS
    # ==========================================

    def calculate_data_rate(self):
        """Calculates Rx Frequency (Hz) over the last second"""
        now = datetime.now()
        dt = (now - self.last_fps_time).total_seconds()
        if dt > 0:
            self.current_freq_hz = self.fps_packet_count / dt
            self.fps_packet_count = 0
            self.last_fps_time = now
            
            # Update labels
            self.lbl_hz.setText(f"Data Rate: {self.current_freq_hz:.1f} Hz")
            self.lbl_packets.setText(f"Packets Rx: {self.packet_count}")

    def refresh_ui_elements(self):
        """
        Main 20fps UI update task:
        1. Identifies max/noisiest sensors
        2. Renders time waveform and power spectrum curves
        3. Updates spatial heatmap
        4. Updates diagnostic bargraphs
        5. Computes statistics panel
        """
        if not self.conn.running or self.packet_count == 0:
            return

        # 1. Hotspot Identification & Signal Isolation
        # Get active array based on calibration toggle
        active_buffer = self.calibrated_history if self.baseline is not None else self.raw_history
        raw_buffer = self.raw_history
        
        # Calculate Peak-to-Peak (ptp) variance of each channel over the last 2 seconds (100 samples)
        recent_window = active_buffer[:, -100:]
        variances = np.ptp(recent_window, axis=1)
        noisiest_idx = int(np.argmax(variances))
        max_variance = variances[noisiest_idx]

        # Get latest frame
        latest_frame = active_buffer[:, -1].tolist()
        max_idx = int(np.argmax(latest_frame))

        # 2. Update Heatmap Grids
        self.heatmap.update_data(latest_frame, noisiest_idx=noisiest_idx, max_idx=max_idx, max_val=self.current_max_scale)
        self.heatmap_linear.update_data(latest_frame, noisiest_idx=noisiest_idx, max_idx=max_idx, max_val=self.current_max_scale)

        # 3. Throttled diagnostic bargraph update (visually smoother)
        if self.time_index % 2 == 0:
            for i in range(40):
                val = int(latest_frame[i])
                bar, lbl_val, _ = self.channel_bars[i]
                bar.setValue(min(val, self.current_max_scale))
                lbl_val.setText(str(val))

        # 4. Extract target wave depending on selected source
        source_idx = self.cb_graph_source.currentIndex()
        if source_idx == 0:
            # Selected Channel
            target_signal = active_buffer[self.selected_channel, :]
            self.plot_time.setTitle(f"1. RAW WAVEFORM OVER TIME (Channel {self.selected_channel})")
        elif source_idx == 1:
            # Average of All Channels
            target_signal = np.mean(active_buffer, axis=0)
            self.plot_time.setTitle("1. AVERAGE MAT INTENSITY WAVEFORM")
        elif source_idx == 2:
            # Max Value Channel
            target_signal = active_buffer[max_idx, :]
            self.plot_time.setTitle(f"1. WAVEFORM: Max Pressure Sensor (Channel {max_idx})")
        else:
            # Noisiest Channel
            target_signal = active_buffer[noisiest_idx, :]
            self.plot_time.setTitle(f"1. WAVEFORM: Noisiest Sensor (Channel {noisiest_idx})")

        # 5. Draw Time Waveform
        self.time_curve.setData(target_signal)

        # 6. Calculate & Draw FFT
        # Remove DC Offset (Subtract mean) to visualize alternating pressure wave
        ac_signal = target_signal - np.mean(target_signal)
        window = np.hamming(self.history_size)
        
        # Apply Hamming window to avoid spectral leakage
        fft_res = np.fft.rfft(ac_signal * window)
        fft_mag = np.abs(fft_res)
        
        # Reset the static DC values
        fft_mag[0:2] = 0.0
        
        # Freq array matching 50Hz sample rate (Nyquist range 0-25 Hz)
        freqs = np.fft.rfftfreq(self.history_size, d=1/50.0)
        self.fft_curve.setData(freqs, fft_mag)

        # 7. Update Statistics Panel
        sig_min = int(np.min(target_signal))
        sig_max = int(np.max(target_signal))
        sig_avg = int(np.mean(target_signal))
        sig_p2p = int(np.ptp(target_signal[-100:])) # latest 2-second P2P

        # Simple Signal-to-Noise Ratio (SNR) Estimation
        # Signal amplitude (AC peak-to-peak) divided by standard deviation of high-frequency noise
        # We estimate high frequency noise by calculating highpass filtered signal std dev
        std_val = np.std(ac_signal)
        if std_val > 0.0:
            # Using peak signal value to rms noise ratio
            est_snr_db = 20 * np.log10(sig_max / std_val)
            snr_str = f"{est_snr_db:.1f} dB"
        else:
            snr_str = "Inf"

        self.stat_min.value_label.setText(str(sig_min))
        self.stat_max.value_label.setText(str(sig_max))
        self.stat_avg.value_label.setText(str(sig_avg))
        self.stat_p2p.value_label.setText(str(sig_p2p))
        self.stat_snr.value_label.setText(snr_str)
        
        # If noise is high, set SNR or status text styles
        if sig_p2p > 4000:
            self.stat_p2p.value_label.setStyleSheet("color: #ff3333; font-size: 18px; font-family: monospace; font-weight: bold;")
        else:
            self.stat_p2p.value_label.setStyleSheet("color: #00ff9d; font-size: 18px; font-family: monospace; font-weight: bold;")

        self.time_index += 1

    def apply_dark_theme(self):
        """Sleek and modern dark-mode stylesheet for medical/hardware diagnostics"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #121212;
            }
            
            QFrame#HeaderCard {
                background-color: #1a1a1a;
                border: 1px solid #2d2d2d;
                border-radius: 8px;
            }
            
            QLabel {
                color: #e0e0e0;
                font-size: 12px;
            }
            
            QGroupBox {
                border: 1px solid #2d2d2d;
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
            
            QComboBox, QLineEdit, QSpinBox {
                background-color: #222;
                border: 1px solid #333;
                border-radius: 4px;
                padding: 4px 8px;
                color: #fff;
                font-family: monospace;
                min-height: 20px;
            }
            
            QComboBox:disabled, QSpinBox:disabled {
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
                background-color: #2b2b2b;
                border-color: #00ff9d;
            }
            
            QPushButton:pressed {
                background-color: #111;
            }
            
            QPushButton#BtnConnect {
                background-color: #0088ff;
                color: #fff;
                font-size: 12px;
            }
            QPushButton#BtnConnect:hover {
                background-color: #0099ff;
                border-color: #00ff9d;
            }
            
            QPushButton#BtnCalibrate {
                background-color: #222;
                color: #ff9d00;
                border: 1px solid #ff9d00;
            }
            QPushButton#BtnCalibrate:hover {
                background-color: #3b2c00;
            }
            QPushButton#BtnCalibrate:disabled {
                border-color: #444;
                color: #555;
                background-color: #151515;
            }
            
            QLabel#StatusDisconnected {
                background-color: #ff3333;
                color: #fff;
                font-weight: bold;
                border-radius: 4px;
                font-size: 12px;
            }
            
            QScrollBar:vertical {
                border: none;
                background: #151515;
                width: 10px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #333;
                min-height: 20px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical:hover {
                background: #00ff9d;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                border: none;
                background: none;
            }
            
            QSplitter::handle {
                background-color: #262626;
            }
            QSplitter::handle:horizontal {
                width: 5px;
            }
            QSplitter::handle:horizontal:hover {
                background-color: #00ff9d;
            }
        """)

    def closeEvent(self, event):
        self.conn.stop()
        if self.is_logging and self.log_file:
            self.log_file.close()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Adjust font
    app_font = QFont("Segoe UI", 9)
    app.setFont(app_font)
    
    window = MatTesterApp()
    window.show()
    sys.exit(app.exec())
