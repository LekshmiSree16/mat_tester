import re
import csv
from datetime import datetime

with open('sensitivity_test_main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add QFileDialog to imports
content = content.replace(
    'QCheckBox, QSpinBox, QTextEdit, QLineEdit, QScrollArea, QSplitter, QFrame, QTabWidget)',
    'QCheckBox, QSpinBox, QTextEdit, QLineEdit, QScrollArea, QSplitter, QFrame, QTabWidget, QFileDialog)'
)

# 2. Add self.sensitivity_array
content = content.replace(
    'self.tested_channels_data = [] # List to store results for CSV',
    'self.tested_channels_data = [] # List to store results for CSV\n        self.sensitivity_array = np.zeros(40)'
)

# 3. Change heatmap title
content = content.replace(
    'self.heatmap = PressureHeatmapWidget("Patient Monitor Map (Swapped)"',
    'self.heatmap = PressureHeatmapWidget("Sensitivity Map (Swapped)"'
)

# 4. Add Load button
btn_save_report_block = '''        self.btn_save_report = QPushButton("Save Report (CSV)")
        self.btn_save_report.clicked.connect(self.save_sensitivity_report)
        self.btn_save_report.setStyleSheet("background-color: #0088ff; font-weight: bold;")'''
btn_load_report_block = btn_save_report_block + '''
        
        self.btn_load_report = QPushButton("Load Report (CSV)")
        self.btn_load_report.clicked.connect(self.load_sensitivity_report)
        self.btn_load_report.setStyleSheet("background-color: #333333; font-weight: bold;")'''
content = content.replace(btn_save_report_block, btn_load_report_block)

sens_panel_layout_block = '''        sens_panel_layout.addWidget(self.btn_capture_loaded, 1, 1)
        sens_panel_layout.addWidget(self.btn_save_report, 1, 2)
        
        sens_panel_layout.addWidget(self.lbl_sens_ch, 2, 0)
        sens_panel_layout.addWidget(self.lbl_sens_noload, 2, 1)
        sens_panel_layout.addWidget(self.lbl_sens_loaded, 3, 0)
        sens_panel_layout.addWidget(self.lbl_sens_diff, 3, 1)
        sens_panel_layout.addWidget(self.lbl_sens_val, 4, 0, 1, 2)'''
sens_panel_layout_new = '''        sens_panel_layout.addWidget(self.btn_capture_loaded, 1, 1)
        sens_panel_layout.addWidget(self.btn_save_report, 1, 2)
        sens_panel_layout.addWidget(self.btn_load_report, 1, 3)
        
        sens_panel_layout.addWidget(self.lbl_sens_ch, 2, 0)
        sens_panel_layout.addWidget(self.lbl_sens_noload, 2, 1)
        sens_panel_layout.addWidget(self.lbl_sens_loaded, 3, 0)
        sens_panel_layout.addWidget(self.lbl_sens_diff, 3, 1)
        sens_panel_layout.addWidget(self.lbl_sens_val, 4, 0, 1, 4)'''
content = content.replace(sens_panel_layout_block, sens_panel_layout_new)

# 5. Remove self.heatmap.update_data from refresh_ui_elements
# The original code has:
#         self.heatmap.update_data(latest_frame, noisiest_idx=noisiest_idx, max_idx=max_idx, max_val=self.current_max_scale)
#         self.heatmap_linear.update_data(latest_frame, noisiest_idx=noisiest_idx, max_idx=max_idx, max_val=self.current_max_scale)
refresh_ui_block = '''        # 2. Update Heatmap Grids
        self.heatmap.update_data(latest_frame, noisiest_idx=noisiest_idx, max_idx=max_idx, max_val=self.current_max_scale)
        self.heatmap_linear.update_data(latest_frame, noisiest_idx=noisiest_idx, max_idx=max_idx, max_val=self.current_max_scale)'''
refresh_ui_new = '''        # 2. Update Heatmap Grids (Only linear updates live pressure, Swapped is now Sensitivity Map)
        # self.heatmap is manually updated in update_sensitivity_map
        self.heatmap_linear.update_data(latest_frame, noisiest_idx=noisiest_idx, max_idx=max_idx, max_val=self.current_max_scale)'''
content = content.replace(refresh_ui_block, refresh_ui_new)

# 6. Append new methods and modify update_sensitivity_calc
update_sens_old = '''        self.tested_channels_data = [r for r in self.tested_channels_data if r['Channel'] != self.selected_channel]
        self.tested_channels_data.append(record)

    def save_sensitivity_report(self):'''
update_sens_new = '''        self.tested_channels_data = [r for r in self.tested_channels_data if r['Channel'] != self.selected_channel]
        self.tested_channels_data.append(record)
        self.sensitivity_array[self.selected_channel] = self.test_sensitivity_val
        self.update_sensitivity_map()

    def update_sensitivity_map(self):
        max_sens = np.max(self.sensitivity_array)
        if max_sens <= 0.0:
            max_sens = 1.0 # Prevent division by zero
        # Update the grid
        self.heatmap.update_data(self.sensitivity_array.tolist(), max_val=max_sens)

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
                        
                        record = {
                            'Channel': ch,
                            'Weight': weight,
                            'NoLoad': noload,
                            'Loaded': loaded,
                            'Diff': diff,
                            'Sensitivity': sens
                        }
                        self.tested_channels_data.append(record)
                        if 0 <= ch < 40:
                            self.sensitivity_array[ch] = sens
                
                self.update_sensitivity_map()
                print(f"Loaded {len(self.tested_channels_data)} records from {file_name}")
            except Exception as e:
                print(f"Failed to load CSV: {e}")

    def save_sensitivity_report(self):'''
content = content.replace(update_sens_old, update_sens_new)

with open('sensitivity_test_main.py', 'w', encoding='utf-8') as f:
    f.write(content)
