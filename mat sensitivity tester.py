"""
Luxisens Optical Fiber Mat Sensitivity Tester launcher
"""
import sys
from PySide6.QtWidgets import QApplication
from mat_sensitivity_tester import MatSensitivityTesterApp

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MatSensitivityTesterApp()
    window.show()
    sys.exit(app.exec())
