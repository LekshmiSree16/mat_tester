import re
import csv
from datetime import datetime

with open('sensitivity_test_main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Rename Class and window title
content = content.replace('class MatTesterApp(QMainWindow):', 'class SensitivityTestMainApp(QMainWindow):')
content = content.replace('self.setWindowTitle("Luxisens Optical Fiber Mat Tester & Analyzer")', 'self.setWindowTitle("Luxisens Mat Sensitivity Tester")')

# 2. State variables
state_vars = '''        self.selected_channel = 11  # Default to channel 11
        self.current_max_scale = 32000
        
        # Sensitivity Test State
        self.test_no_load_val = 0.0
        self.test_loaded_val = 0.0
        self.test_sensitivity_val = 0.0
        self.tested_channels_data = [] # List to store results for CSV'''
content = content.replace('        self.selected_channel = 11  # Default to channel 11\n        self.current_max_scale = 32000', state_vars)

# 3. AT Command console signals
signals_old = '''        self.conn.new_frame_signal.connect(self.handle_new_frame)
        self.conn.connection_status_signal.connect(self.handle_connection_status)
        self.conn.at_command_received_signal.connect(self.handle_at_command_received)
        self.conn.at_command_sent_signal.connect(self.handle_at_command_sent)
        self.conn.new_rwav_signal.connect(self.handle_new_rwav)
        self.conn.new_rr_value_signal.connect(self.handle_new_rr_value)'''
signals_new = '''        self.conn.new_frame_signal.connect(self.handle_new_frame)
        self.conn.connection_status_signal.connect(self.handle_connection_status)'''
content = content.replace(signals_old, signals_new)

# 4. Remove console_group from UI
console_group_old = '''        # Group B: AT Command Console
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

        left_layout.addWidget(console_group, 1)'''
content = content.replace(console_group_old, '        left_layout.addStretch(1)')

# 5. Replace Respiration Wave Panel with Sensitivity Test Controls
resp_panel_old = '''        # Respiration Wave Panel (Bedside Monitor style)
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

        right_layout.addWidget(resp_panel_group)'''
sens_panel_new = '''        # Sensitivity Test Panel
        sens_panel_group = QGroupBox("Sensitivity Test Controls")
        sens_panel_layout = QGridLayout(sens_panel_group)
        sens_panel_layout.setContentsMargins(10, 10, 10, 10)
        sens_panel_layout.setSpacing(10)
        
        lbl_weight = QLabel("Applied Weight (grams):")
        lbl_weight.setStyleSheet("font-weight: bold; color: #aaa;")
        self.sp_weight = QSpinBox()
        self.sp_weight.setRange(1, 100000)
        self.sp_weight.setValue(1000)
        
        self.btn_capture_noload = QPushButton("Capture No Load (Baseline)")
        self.btn_capture_noload.clicked.connect(self.capture_no_load)
        
        self.btn_capture_loaded = QPushButton("Capture Loaded Value")
        self.btn_capture_loaded.clicked.connect(self.capture_loaded)
        
        self.btn_save_report = QPushButton("Save Report (CSV)")
        self.btn_save_report.clicked.connect(self.save_sensitivity_report)
        self.btn_save_report.setStyleSheet("background-color: #0088ff; font-weight: bold;")
        
        self.lbl_sens_ch = QLabel(f"Selected Channel: {self.selected_channel}")
        self.lbl_sens_noload = QLabel("No Load Avg: --")
        self.lbl_sens_loaded = QLabel("Loaded Avg: --")
        self.lbl_sens_diff = QLabel("Difference: --")
        self.lbl_sens_val = QLabel("Sensitivity: -- units/gram")
        
        # Styles for test labels
        for lbl in [self.lbl_sens_ch, self.lbl_sens_noload, self.lbl_sens_loaded, self.lbl_sens_diff, self.lbl_sens_val]:
            lbl.setStyleSheet("color: #00ff9d; font-size: 14px; font-weight: bold;")
        
        sens_panel_layout.addWidget(lbl_weight, 0, 0)
        sens_panel_layout.addWidget(self.sp_weight, 0, 1)
        sens_panel_layout.addWidget(self.btn_capture_noload, 1, 0)
        sens_panel_layout.addWidget(self.btn_capture_loaded, 1, 1)
        sens_panel_layout.addWidget(self.btn_save_report, 1, 2)
        
        sens_panel_layout.addWidget(self.lbl_sens_ch, 2, 0)
        sens_panel_layout.addWidget(self.lbl_sens_noload, 2, 1)
        sens_panel_layout.addWidget(self.lbl_sens_loaded, 3, 0)
        sens_panel_layout.addWidget(self.lbl_sens_diff, 3, 1)
        sens_panel_layout.addWidget(self.lbl_sens_val, 4, 0, 1, 2)
        
        right_layout.addWidget(sens_panel_group)'''
content = content.replace(resp_panel_old, sens_panel_new)

# 6. Replace txt_console.append
content = re.sub(r'self\.txt_console\.append\(.*?<span[^>]*>(.*?)</span>.*?\)', r'print("\1")', content)
content = content.replace('self.txt_console.append(f"<span style=\'color:red;\'>System: {msg}</span>")', 'print(f"System: {msg}")')
content = content.replace('self.txt_console.append(f"<span style=\'color:#00ff9d;\'>System: {msg}</span>")', 'print(f"System: {msg}")')
content = content.replace('self.txt_console.append(f"<span style=\'color:yellow;\'>System: Sensitivity set to {val} (will apply on connect)</span>")', 'print(f"System: Sensitivity set to {val} (will apply on connect)")')


# 7. Add label updates on change channel
change_ch_old = '''                    QProgressBar::chunk { 
                        background-color: #0088ff; 
                        border-radius: 3px;
                    }
                """)'''
change_ch_new = change_ch_old + '''
        
        self.lbl_sens_ch.setText(f"Selected Channel: {val}")
        # Reset sensitivity values for this channel
        self.test_no_load_val = 0.0
        self.test_loaded_val = 0.0
        self.test_sensitivity_val = 0.0
        self.lbl_sens_noload.setText("No Load Avg: --")
        self.lbl_sens_loaded.setText("Loaded Avg: --")
        self.lbl_sens_diff.setText("Difference: --")
        self.lbl_sens_val.setText("Sensitivity: -- units/gram")'''
content = content.replace(change_ch_old, change_ch_new)

# 8. Remove custom cmd send functions
cmd_fns = '''    def send_custom_cmd(self):
        cmd = self.txt_cmd_input.text().strip()
        if cmd:
            self.send_console_command(cmd)
            self.txt_cmd_input.clear()

    def send_console_command(self, cmd):
        if self.conn.running:
            self.conn.send_command(cmd)
        else:
            self.txt_console.append(f"<span style='color:red;'>System: Connect to send command '{cmd}'</span>")'''
content = content.replace(cmd_fns, '')

# 9. Clean up handle_connection_status disconnected
conn_status_old = '''        else:
            self.lbl_conn_status.setText("DISCONNECTED")
            self.lbl_conn_status.setStyleSheet("background-color: #ff3333; color: #fff; font-weight: bold; border-radius: 4px;")
            self.txt_console.append(f"<span style='color:red;'>System: {msg}</span>")
            self.btn_calibrate.setEnabled(False)
            if hasattr(self, 'wave_widget'):
                self.wave_widget.clear()
            if hasattr(self, 'lbl_rr_val'):
                self.lbl_rr_val.setText("--")'''
conn_status_new = '''        else:
            self.lbl_conn_status.setText("DISCONNECTED")
            self.lbl_conn_status.setStyleSheet("background-color: #ff3333; color: #fff; font-weight: bold; border-radius: 4px;")
            print(f"System: {msg}")
            self.btn_calibrate.setEnabled(False)'''
content = content.replace(conn_status_old, conn_status_new)

# 10. Remove AT/RR handlers
at_rr_handlers = '''    @Slot(float)
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
        self.txt_console.moveCursor(QTextCursor.End)'''
content = content.replace(at_rr_handlers, '')

# Fix stray moveCursor from regex replace if any
content = re.sub(r'self\.txt_console\.moveCursor\(.*?\)\n', '', content)

# 11. Add sensitivity logic methods
sens_methods = '''    def get_current_channel_average(self):
        active_buffer = self.calibrated_history if self.baseline is not None else self.raw_history
        recent_window = active_buffer[self.selected_channel, -50:]
        return np.mean(recent_window)

    def capture_no_load(self):
        self.test_no_load_val = self.get_current_channel_average()
        self.lbl_sens_noload.setText(f"No Load Avg: {self.test_no_load_val:.1f}")
        self.update_sensitivity_calc()
        
    def capture_loaded(self):
        self.test_loaded_val = self.get_current_channel_average()
        self.lbl_sens_loaded.setText(f"Loaded Avg: {self.test_loaded_val:.1f}")
        self.update_sensitivity_calc()
        
    def update_sensitivity_calc(self):
        diff = self.test_loaded_val - self.test_no_load_val
        weight = self.sp_weight.value()
        self.test_sensitivity_val = diff / weight if weight > 0 else 0.0
        
        self.lbl_sens_diff.setText(f"Difference: {diff:.1f}")
        self.lbl_sens_val.setText(f"Sensitivity: {self.test_sensitivity_val:.3f} units/gram")
        
        record = {
            'Channel': self.selected_channel,
            'Weight': weight,
            'NoLoad': self.test_no_load_val,
            'Loaded': self.test_loaded_val,
            'Diff': diff,
            'Sensitivity': self.test_sensitivity_val
        }
        self.tested_channels_data = [r for r in self.tested_channels_data if r['Channel'] != self.selected_channel]
        self.tested_channels_data.append(record)

    def save_sensitivity_report(self):
        if not self.tested_channels_data:
            print("No sensitivity data to save.")
            return
            
        os.makedirs("mat_logs", exist_ok=True)
        filename = f"mat_logs/SensitivityReport_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        try:
            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['Channel', 'Weight (g)', 'No Load Avg', 'Loaded Avg', 'Difference', 'Sensitivity (units/g)'])
                sorted_data = sorted(self.tested_channels_data, key=lambda x: x['Channel'])
                for r in sorted_data:
                    writer.writerow([r['Channel'], r['Weight'], f"{r['NoLoad']:.1f}", f"{r['Loaded']:.1f}", f"{r['Diff']:.1f}", f"{r['Sensitivity']:.3f}"])
            print(f"Report saved to {filename}")
        except Exception as e:
            print(f"Failed to save report: {e}")

    def closeEvent'''
content = content.replace('    def closeEvent', sens_methods)

# 12. Main instantiation
content = content.replace('window = MatTesterApp()', 'window = SensitivityTestMainApp()')

with open('sensitivity_test_main.py', 'w', encoding='utf-8') as f:
    f.write(content)
