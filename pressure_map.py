from PySide6.QtWidgets import (QFrame, QVBoxLayout, QLabel, QGridLayout, QToolTip)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QBrush, QPen

def clamp(n, smallest, largest):
    return max(smallest, min(n, largest))

def get_pressure_color_style(value, max_val=32000):
    """
    Returns a QSS background color string based on pressure value.
    Gradient: Deep Blue/Black (Empty) -> Cyan -> Green -> Yellow -> Orange -> Crimson Red
    """
    norm = min(1.0, value / max_val)
    r, g, b = 0, 0, 0

    if norm <= 0.05:
        # Near black for empty/noise threshold
        factor = norm / 0.05
        r, g, b = 15, int(15 + 25 * factor), int(30 + 70 * factor)
    elif norm <= 0.25:
        t = (norm - 0.05) / 0.20
        r, g, b = int(0 * t), int(40 + 160 * t), int(100 + 155 * t) # transitioning to bright cyan
    elif norm <= 0.5:
        t = (norm - 0.25) / 0.25
        r, g, b = int(0 + 120 * t), int(200 + 55 * t), int(255 * (1 - t)) # transitioning to green-yellow
    elif norm <= 0.75:
        t = (norm - 0.5) / 0.25
        r, g, b = int(120 + 135 * t), int(255 - 125 * t), 0 # transitioning to orange
    else:
        t = (norm - 0.75) / 0.25
        r, g, b = 255, int(130 - 130 * t), 0 # transitioning to crimson red

    return f"#{clamp(r, 0, 255):02x}{clamp(g, 0, 255):02x}{clamp(b, 0, 255):02x}"


class PressureCell(QFrame):
    """
    Individual sensor representation in the grid.
    Supports clicking (to select sensor for plotting) and hover tooltips.
    Uses custom QPainter painting to prevent dynamic style sheet font corruption.
    """
    cell_clicked = Signal(int) # Emits sensor index

    def __init__(self, row, col, sensor_idx, cell_size=64, is_patient_monitor_style=False):
        super().__init__()
        self.row = row
        self.col = col
        self.sensor_idx = sensor_idx
        self.current_value = 0
        self.is_selected = False
        self.is_noisiest = False
        self.is_max_pressure = False
        self.max_val = 32000
        self.is_patient_monitor_style = is_patient_monitor_style

        self.setFixedSize(cell_size, cell_size) 
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(1)

        if self.is_patient_monitor_style:
            # Patient Monitor Style: Coordinate label and value
            self.lbl_idx = None
            
            self.lbl_val = QLabel("0")
            self.lbl_val.setAlignment(Qt.AlignCenter)
            self.lbl_val.setStyleSheet("font-size: 10px; color: #fff; border: none; background: transparent; font-weight: bold; margin: 0px;")
            layout.addWidget(self.lbl_val)
            
            self.lbl_coord = QLabel(f"({row},{col})")
            self.lbl_coord.setAlignment(Qt.AlignCenter)
            self.lbl_coord.setStyleSheet("font-size: 8px; color: #ccc; border: none; background: transparent;")
            layout.addWidget(self.lbl_coord)
        else:
            # Tester App Style: Channel index, real-time value, and coordinate
            idx_size = 9 if cell_size >= 60 else 7
            val_size = 11 if cell_size >= 60 else 9
            coord_size = 8 if cell_size >= 60 else 6

            # Coordinate label (e.g. "Ch 12")
            self.lbl_idx = QLabel(f"Ch {self.sensor_idx}")
            self.lbl_idx.setAlignment(Qt.AlignCenter)
            self.lbl_idx.setStyleSheet(f"font-size: {idx_size}px; color: #ffffff; border: none; background: transparent; font-weight: bold; padding: 0px; margin: 0px;")
            layout.addWidget(self.lbl_idx)

            # Real-time value label
            self.lbl_val = QLabel("0")
            self.lbl_val.setAlignment(Qt.AlignCenter)
            self.lbl_val.setStyleSheet(f"font-size: {val_size}px; color: #00ff9d; border: none; background: transparent; font-weight: bold; padding: 0px; margin: 0px;")
            layout.addWidget(self.lbl_val)

            # Matrix grid cell coordinate label
            self.lbl_coord = QLabel(f"({row},{col})")
            self.lbl_coord.setAlignment(Qt.AlignCenter)
            self.lbl_coord.setStyleSheet(f"font-size: {coord_size}px; color: #bbbbbb; border: none; background: transparent; padding: 0px; margin: 0px;")
            layout.addWidget(self.lbl_coord)

        # Set parent container transparent borders to prevent default QFrame borders
        self.setStyleSheet("background: transparent; border: none;")

        self.update_appearance()

    def update_state(self, value, max_val=32000):
        self.current_value = value
        if self.lbl_val:
            if isinstance(value, float):
                self.lbl_val.setText(f"{value:.2f}")
            else:
                self.lbl_val.setText(str(value))
        self.max_val = max_val
        self.update_appearance()
        self.setToolTip(f"Sensor ID: {self.sensor_idx}\nGrid Location: ({self.row}, {self.col})\nRaw Value: {self.current_value}")

    def update_appearance(self):
        # Triggers standard paintEvent repaint
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Get background color style
        if self.is_patient_monitor_style:
            # Original Patient Monitor Color Mapping (Blue -> Cyan -> Green -> Yellow -> Orange -> Red)
            norm = min(1.0, self.current_value / self.max_val)
            r, g, b = 0, 0, 0
            if norm <= 0.2:  # Blue -> Cyan
                r, g, b = 0, int(150 * (norm / 0.2)), 255
            elif norm <= 0.4:  # Cyan -> Green
                t = (norm - 0.2) / 0.2
                r, g, b = 0, int(150 + 105 * t), int(255 * (1 - t))
            elif norm <= 0.6:  # Green -> Yellow
                t = (norm - 0.4) / 0.2
                r, g, b = int(255 * t), 255, 0
            elif norm <= 0.8:  # Yellow -> Orange
                t = (norm - 0.6) / 0.2
                r, g, b = 255, int(255 * (1 - 0.5 * t)), 0
            else:  # Orange -> Red
                t = (norm - 0.8) / 0.2
                r, g, b = 255, int(128 * (1 - t)), 0
            bg_color = QColor(clamp(r, 0, 255), clamp(g, 0, 255), clamp(b, 0, 255))
        else:
            # Custom Tester Color Mapping (Dark Blue/Black Base)
            bg_hex = get_pressure_color_style(self.current_value, max_val=self.max_val)
            bg_color = QColor(bg_hex)
        
        # Border Priority: Selected > Max Pressure > Noisiest
        if self.is_patient_monitor_style:
            if self.is_selected:
                border_color = QColor("#ffffff")  # Thick solid white border for active channel
                border_width = 2
            else:
                border_color = QColor("#444444")
                border_width = 1
        else:
            if self.is_selected:
                border_color = QColor("#00ff9d")  # Glowing Green
                border_width = 3
            elif self.is_max_pressure:
                border_color = QColor("#ff3333")  # Red
                border_width = 2
            elif self.is_noisiest:
                border_color = QColor("#ffb300")  # Amber
                border_width = 2
            else:
                border_color = QColor("#444444")  # Gray
                border_width = 1

        # Draw filled background rounded rect
        painter.setBrush(QBrush(bg_color))
        painter.setPen(Qt.NoPen)
        rect = self.rect()
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 6, 6)
        
        # Draw border rounded rect
        painter.setBrush(Qt.NoBrush)
        pen = QPen(border_color, border_width)
        if not self.is_patient_monitor_style and self.is_noisiest and not self.is_selected and not self.is_max_pressure:
            pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        
        # Adjust border insets to stay sharp and completely within widget bounds
        inset = border_width // 2 + 1
        painter.drawRoundedRect(rect.adjusted(inset, inset, -inset, -inset), 6, 6)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.cell_clicked.emit(self.sensor_idx)
            event.accept()
        else:
            super().mousePressEvent(event)


class PressureHeatmapWidget(QFrame):
    """
    A grid visualizer that matches the mattress physical layout.
    Connects to connection signals to display active heat maps.
    """
    sensor_selected = Signal(int) # Emits sensor index to parent window

    def __init__(self, title_text="Mattress Layout (8x5)", use_swapped_layout=True, cell_size=48, is_patient_monitor_style=False):
        super().__init__()
        self.selected_sensor = 11 # Default selection (Torso center)
        self.noisiest_sensor = -1
        self.max_sensor = -1
        self.cell_size = cell_size
        self.use_swapped_layout = use_swapped_layout
        self.is_patient_monitor_style = is_patient_monitor_style

        self.setStyleSheet("background-color: #1a1a1a; border: 1px solid #333; border-radius: 10px; padding: 5px;")
        
        # Auto-calculate exact fixed width to align perfectly
        cols = 5
        self.setFixedWidth(cols * cell_size + (cols - 1) * 3 + 18)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        title = QLabel(title_text)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #00ff9d; font-weight: bold; font-size: 11px; border: none; margin-bottom: 5px;")
        layout.addWidget(title)

        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(3)
        self.grid.setVerticalSpacing(3)
        self.grid.setAlignment(Qt.AlignCenter)

        # Hardware coordinate mapping: Sensor ID -> (Row, Col)
        if use_swapped_layout:
            # Swapped Column 1 & 2 layout (Patient Monitor hardware spec due to physical cable twist)
            self.sensor_map = {
                # Column 0 (Indices 0-7)
                0: (0, 0), 1: (1, 0), 2: (2, 0), 3: (3, 0), 4: (4, 0), 5: (5, 0), 6: (6, 0), 7: (7, 0),
                # Column 2 (Indices 8-15) - SWAPPED (Col index 2)
                8: (0, 2), 9: (1, 2), 10: (2, 2), 11: (3, 2), 12: (4, 2), 13: (5, 2), 14: (6, 2), 15: (7, 2),
                # Column 1 (Indices 16-23) - SWAPPED (Col index 1)
                16: (0, 1), 17: (1, 1), 18: (2, 1), 19: (3, 1), 20: (4, 1), 21: (5, 1), 22: (6, 1), 23: (7, 1),
                # Column 3 (Indices 24-31)
                24: (0, 3), 25: (1, 3), 26: (2, 3), 27: (3, 3), 28: (4, 3), 29: (5, 3), 30: (6, 3), 31: (7, 3),
                # Column 4 (Indices 32-39)
                32: (0, 4), 33: (1, 4), 34: (2, 4), 35: (3, 4), 36: (4, 4), 37: (5, 4), 38: (6, 4), 39: (7, 4)
            }
        else:
            # Linear Standard Layout (No twist correction)
            self.sensor_map = {
                # Column 0 (Indices 0-7)
                0: (0, 0), 1: (1, 0), 2: (2, 0), 3: (3, 0), 4: (4, 0), 5: (5, 0), 6: (6, 0), 7: (7, 0),
                # Column 1 (Indices 8-15) - Linear (Col index 1)
                8: (0, 1), 9: (1, 1), 10: (2, 1), 11: (3, 1), 12: (4, 1), 13: (5, 1), 14: (6, 1), 15: (7, 1),
                # Column 2 (Indices 16-23) - Linear (Col index 2)
                16: (0, 2), 17: (1, 2), 18: (2, 2), 19: (3, 2), 20: (4, 2), 21: (5, 2), 22: (6, 2), 23: (7, 2),
                # Column 3 (Indices 24-31)
                24: (0, 3), 25: (1, 3), 26: (2, 3), 27: (3, 3), 28: (4, 3), 29: (5, 3), 30: (6, 3), 31: (7, 3),
                # Column 4 (Indices 32-39)
                32: (0, 4), 33: (1, 4), 34: (2, 4), 35: (3, 4), 36: (4, 4), 37: (5, 4), 38: (6, 4), 39: (7, 4)
            }

        # Inverse mapping: (Row, Col) -> Sensor ID
        self.cell_widgets = {} # maps sensor_idx -> cell widget

        # Create Cells
        for sensor_idx, (r, c) in self.sensor_map.items():
            cell = PressureCell(r, c, sensor_idx, cell_size=cell_size, is_patient_monitor_style=self.is_patient_monitor_style)
            cell.cell_clicked.connect(self._handle_cell_clicked)
            self.grid.addWidget(cell, r, c)
            self.cell_widgets[sensor_idx] = cell

        # Highlight default selected sensor
        if self.selected_sensor in self.cell_widgets:
            self.cell_widgets[self.selected_sensor].is_selected = True
            self.cell_widgets[self.selected_sensor].update_appearance()

        layout.addLayout(self.grid)

    def _handle_cell_clicked(self, sensor_idx):
        if self.selected_sensor == sensor_idx and self.cell_widgets[sensor_idx].is_selected:
            return
            
        # Deselect old sensor
        if self.selected_sensor in self.cell_widgets:
            self.cell_widgets[self.selected_sensor].is_selected = False
            self.cell_widgets[self.selected_sensor].update_appearance()

        # Select new sensor
        self.selected_sensor = sensor_idx
        if self.selected_sensor in self.cell_widgets:
            self.cell_widgets[self.selected_sensor].is_selected = True
            self.cell_widgets[self.selected_sensor].update_appearance()

        # Emit signal to parent
        self.sensor_selected.emit(sensor_idx)

    def select_sensor_programmatically(self, sensor_idx):
        """Allows external controls (like the channel bargraph list) to change selections"""
        if 0 <= sensor_idx < 40:
            self._handle_cell_clicked(sensor_idx)

    def update_data(self, values, noisiest_idx=-1, max_idx=-1, max_val=32000):
        """
        Updates grid data values.
        Supports automatic highlighting of max pressure sensor and noisiest sensor.
        """
        if not values:
            return

        # Update noise and maximum indicators
        self.noisiest_sensor = noisiest_idx
        self.max_sensor = max_idx

        for idx, cell in self.cell_widgets.items():
            if idx < len(values):
                cell.is_noisiest = (idx == self.noisiest_sensor)
                cell.is_max_pressure = (idx == self.max_sensor)
                cell.update_state(values[idx], max_val=max_val)
