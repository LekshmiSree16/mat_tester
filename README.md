# Luxisens Optical Fiber Mat Tester

A comprehensive desktop utility written in Python with PySide6 to test, calibrate, and analyze the signals from custom optical fiber mats (pressure-sensing mattresses).

## Features

- **Multi-Source Data Streaming**:
  - **Serial (USB)**: Directly connects to STM32 boards (auto-detects virtual COM ports) at up to 921600 baud.
  - **Wi-Fi (DataGram-6060)**: Captures passive network broadcasts from other monitor displays on port 6060.
  - **Mat Simulator**: Generates synthetic respiration waveforms (with custom frequency & noise aliases) to test UI and analysis features without hardware.
- **Physical Layout Heatmap**:
  - Displays the 8x5 (40-sensor) hardware map corresponding to the patient monitor's physical mattress sensor locations.
  - Provides hover tooltips showing raw value, channel ID, and coordinates.
  - Auto-highlights the highest-pressure sensor and the noisiest sensor.
  - Clicking any grid cell targets it for real-time waveform graphing.
- **Individual Channel Bargraphs**: Shows the real-time value of all 40 fibers side-by-side to instantly spot dead or unresponsive channels.
- **Real-Time Analytics Dashboard**: Tracks Minimum, Maximum, Average, Peak-to-Peak (P2P) Variance, and estimated Signal-to-Noise Ratio (SNR).
- **Dual PyQtGraph Scopes**:
  - **Time-Domain Waveform**: Traces respiration curves and signal expansion over 10 seconds.
  - **Frequency-Domain FFT**: Runs real-time Fast Fourier Transforms (0-25 Hz) to pinpoint 50/60Hz AC mains power interference or mechanical vibration noise.
- **AT Command Console**:
  - Interactive terminal showing outgoing and incoming AT commands.
  - Short-cut buttons for common firmware settings (`AT+VER`, `AT+MATMOD`, `AT+INTT`).
  - Text input to send arbitrary custom commands.
- **Zero-Calibration Routine**: Collects a 50-frame baseline and dynamically subtracts it from live data to isolate movement changes.
- **CSV Data Logging**: Records time-stamped raw sensor readings to `mat_logs/` for offline scientific analysis (in MATLAB, Python, Excel, etc.).

---

## Installation & Setup

Make sure you have Python 3.8+ installed.

1. **Navigate to the application folder**:
   ```bash
   cd C:\Users\Admin\Desktop\mat_tester
   ```

2. **Install dependencies**:
   ```bash
   pip install PySide6 pyqtgraph numpy pyserial
   ```

3. **Run the Mat Tester**:
   ```bash
   python main.py
   ```

---

## Technical Specifications

- **Expected Data Frequency**: 50 Hz (20ms interval per frame).
- **Communication Protocol**:
  - Data frames should be sent in the following format over Serial/UDP:
    `AT+SDATA val0,val1,val2,...,val39` (where values represent 12-bit or 15-bit raw ADC intensity values).
  - Supports interleaved index pairs:
    `AT+SDATA idx0,val0,idx1,val1,...,idx39,val39`.
- **Supported AT Commands**:
  - `AT+VER`: Queries the current firmware version.
  - `AT+INTT <value>`: Sets the sensor integration time/sensitivity.
  - `AT+MATMOD <Adult/NeoNat>`: Updates the firmware processing algorithms to match target patient types.
"# mat_tester" 
