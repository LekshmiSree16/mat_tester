import math
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QLinearGradient, QPainterPath

class BreathingWaveformWidget(QWidget):
    """
    Renders the exact respiration waveform (cyan line with a fading blue gradient fill)
    exactly matching the visual style of the Patient Monitor.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(100)
        self.data = [0.0] * 300
        self.baseline = None
        self.alpha = 0.005 # Slower baseline tracking for baseline removal filter

    def push_sample(self, value):
        """
        Receives real-time wave samples (e.g. from AT+RWAV).
        Applies a high-pass IIR filter to remove baseline drift and centres the wave.
        """
        if value is None:
            return
        
        # Simple IIR High Pass Filter for baseline drift removal
        if self.baseline is None:
            self.baseline = value
        else:
            self.baseline += self.alpha * (value - self.baseline)
            
        y = value - self.baseline
        
        # Store sample and keep buffer at max 300 points
        self.data.append(y)
        if len(self.data) > 300:
            self.data.pop(0)
            
        self.update() # Triggers repaint

    def clear(self):
        """Resets the waveform data"""
        self.data = [0.0] * 300
        self.baseline = None
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        w = self.width()
        h = self.height()
        cy = h / 2

        # 1. Background Fill (Very dark charcoal, almost black)
        painter.fillRect(0, 0, w, h, QBrush(QColor("#080a10")))

        # 2. Draw Blue Grid Lines (Matches Patient Monitor style #1a2540)
        painter.setPen(QPen(QColor("#1a2540"), 1))
        for y in range(5):
            y_pos = (y / 4) * h
            painter.drawLine(0, y_pos, w, y_pos)

        # 3. Waveform Path
        path = QPainterPath()
        
        # Compute absolute maximum to auto-scale amplitude dynamically
        vals = [abs(v) for v in self.data]
        max_abs = max(vals) if vals else 0
        
        # Hard floor to prevent tiny noise squiggles from scaling full-screen
        if max_abs < 15.0:
            max_abs = 15.0
            
        scale = (h * 0.4) / max_abs
        
        for i, v in enumerate(self.data):
            x = (i / (len(self.data) - 1)) * w
            y = cy - v * scale
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)

        # 4. Draw Fading Fill Gradient Under the Wave
        fill_path = QPainterPath(path)
        fill_path.lineTo(w, h)
        fill_path.lineTo(0, h)
        fill_path.closeSubpath()
        
        fill_grad = QLinearGradient(0, 0, 0, h)
        fill_grad.setColorAt(0, QColor(0, 212, 255, 30))  # #00d4ff1e
        fill_grad.setColorAt(1, QColor(0, 212, 255, 2))   # #00d4ff02
        painter.fillPath(fill_path, QBrush(fill_grad))

        # 5. Draw Glowing Neon Cyan Line on Top
        painter.setPen(QPen(QColor("#00d4ff"), 2.5)) 
        painter.drawPath(path)
