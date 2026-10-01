import sys
import serial
import serial.tools.list_ports
import threading
import time
import socket
import queue
import numpy as np
from PySide6.QtCore import QObject, Signal

class IsolatedConnectionManager(QObject):
    """
    Manages data input from three possible sources:
    1. Physical Serial (COM) Port
    2. DataGram Wi-Fi Broadcast (Port 6060)
    3. Live Mattress Simulator (for testing without hardware)

    Thread-safe implementation that emits PySide6 signals.
    """
    new_frame_signal = Signal(list)                # Emits list of sensor values (e.g., 40)
    connection_status_signal = Signal(str, bool)   # Emits (status_message, is_connected)
    at_command_received_signal = Signal(str)       # Emits incoming AT commands for the log console
    at_command_sent_signal = Signal(str)           # Emits sent commands for console log
    new_rwav_signal = Signal(float)                # Emits real-time breathing waveform samples
    new_rr_value_signal = Signal(int)              # Emits real-time Respiration Rate (BPM) values

    def __init__(self):
        super().__init__()
        self.serial_conn = None
        self.udp_sock = None
        
        self.running = False
        self.mode = None # "serial", "udp", "simulator", or None
        self.thread = None
        self.command_queue = queue.Queue()
        self.write_thread = None

        # Simulator State
        self.sim_breath_rate = 15.0 # Breaths per minute (Adult default)
        self.sim_sensitivity = 1.0 # Sensitivity multiplier
        self.sim_firmware_ver = "LuxisensMat-Sim-v2.1"
        self.sim_mode = "Adult"

    def get_ports(self):
        """Returns a list of available serial ports"""
        try:
            ports = serial.tools.list_ports.comports()
            return [f"{p.device} - {p.description}" for p in ports]
        except Exception as e:
            return [f"Error listing ports: {e}"]

    def start_serial(self, port_name, baud_rate=921600):
        """Connects via Serial Port"""
        self.stop()
        try:
            self.serial_conn = serial.Serial(port_name, baud_rate, timeout=1)
            self.running = True
            self.mode = "serial"
            
            # Start reader loop
            self.thread = threading.Thread(target=self._serial_read_loop, daemon=True)
            self.thread.start()
            
            # Start writer loop
            self.write_thread = threading.Thread(target=self._serial_write_loop, daemon=True)
            self.write_thread.start()
            
            # Handshake query
            self.send_command("AT+VER")
            
            self.connection_status_signal.emit(f"Connected to {port_name} ({baud_rate})", True)
            return True
        except Exception as e:
            self.connection_status_signal.emit(f"Serial Connection Error: {e}", False)
            self.stop()
            return False

    def start_udp(self, port=6060):
        """Connects via DataGram Wi-Fi Broadcast"""
        self.stop()
        try:
            self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.udp_sock.bind(('', port))
            self.running = True
            self.mode = "udp"
            
            self.thread = threading.Thread(target=self._udp_read_loop, daemon=True)
            self.thread.start()
            
            self.connection_status_signal.emit(f"Listening on DataGram Port {port}", True)
            return True
        except Exception as e:
            self.connection_status_signal.emit(f"DataGram Bind Error: {e}", False)
            self.stop()
            return False

    def start_simulator(self):
        """Starts the Mattress Signal Simulator"""
        self.stop()
        self.running = True
        self.mode = "simulator"
        
        self.thread = threading.Thread(target=self._simulator_loop, daemon=True)
        self.thread.start()
        
        self.connection_status_signal.emit("Simulator Active (Adult Mat Mode)", True)
        return True

    def stop(self):
        """Disconnects or stops any active source"""
        self.running = False
        
        # Clear queue
        while not self.command_queue.empty():
            try:
                self.command_queue.get_nowait()
            except queue.Empty:
                break
                
        # Close Serial
        if self.serial_conn:
            try:
                if self.serial_conn.is_open:
                    self.serial_conn.close()
            except:
                pass
            self.serial_conn = None
            
        # Close UDP
        if self.udp_sock:
            try:
                self.udp_sock.close()
            except:
                pass
            self.udp_sock = None
            
        # Wait for threads
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=0.5)
        self.thread = None
        
        if self.write_thread and self.write_thread.is_alive():
            self.write_thread.join(timeout=0.5)
        self.write_thread = None
        
        self.mode = None
        self.connection_status_signal.emit("Disconnected", False)

    def send_command(self, cmd_str):
        """Sends an AT command string to the mat (or simulator)"""
        cmd_str = cmd_str.strip()
        if not cmd_str:
            return
            
        # Log command sent
        self.at_command_sent_signal.emit(cmd_str)
        
        if self.mode == "serial":
            self.command_queue.put(cmd_str)
        elif self.mode == "simulator":
            # Direct simulation callback after a tiny thread-safe delay
            threading.Thread(target=self._handle_simulated_command, args=(cmd_str,), daemon=True).start()
        elif self.mode == "udp":
            self.at_command_received_signal.emit("Error: Cannot send AT commands over passive UDP listener.")

    # ==========================================================
    #  READER/WRITER THREAD LOOPS
    # ==========================================================

    def _serial_read_loop(self):
        while self.running and self.serial_conn and self.serial_conn.is_open:
            try:
                if self.serial_conn.in_waiting:
                    line_bytes = self.serial_conn.readline()
                    line = line_bytes.decode('utf-8', errors='ignore').strip()
                    if line:
                        self._parse_incoming_line(line)
                else:
                    time.sleep(0.002) # 2ms sleep
            except Exception as e:
                if self.running:
                    self.connection_status_signal.emit(f"Read Loop Error: {e}", False)
                break
        self.running = False

    def _serial_write_loop(self):
        while self.running and self.serial_conn and self.serial_conn.is_open:
            try:
                try:
                    cmd = self.command_queue.get(timeout=0.1)
                    if not cmd.endswith("\r\n"):
                        cmd += "\r\n"
                    self.serial_conn.write(cmd.encode('ascii'))
                except queue.Empty:
                    continue
            except Exception as e:
                break

    def _udp_read_loop(self):
        while self.running and self.udp_sock:
            try:
                data, addr = self.udp_sock.recvfrom(8192)
                if data:
                    line = data.decode('utf-8', errors='ignore').strip()
                    if line:
                        self._parse_incoming_line(line)
            except OSError:
                break # Normal when closed
            except Exception as e:
                if self.running:
                    self.connection_status_signal.emit(f"UDP Error: {e}", False)
                break
        self.running = False

    def _parse_incoming_line(self, line):
        """Routes lines from Serial/UDP to parser"""
        if line.startswith("AT+SDATA"):
            payload = line.replace("AT+SDATA", "").strip()
            try:
                # Support index-value pairs or straight arrays
                vals = [int(x) for x in payload.split(',') if x.strip()]
                
                # Check for 80-length interleaved format [idx, val, idx, val...]
                if len(vals) == 80:
                    vals = [vals[i] for i in range(1, 80, 2)]
                
                if vals:
                    self.new_frame_signal.emit(vals)
            except ValueError:
                pass
        elif line.startswith("AT+RWAV"):
            try:
                payload = line.replace("AT+RWAV", "").strip()
                parts = [float(x) for x in payload.split(',') if x.strip()]
                for val in parts:
                    self.new_rwav_signal.emit(val)
            except ValueError:
                pass
            self.at_command_received_signal.emit(line)
        elif line.startswith("AT+RR"):
            try:
                val_str = line.replace("AT+RR", "").strip()
                val = int(val_str)
                self.new_rr_value_signal.emit(val)
            except ValueError:
                pass
            self.at_command_received_signal.emit(line)
        else:
            # Broadcast other AT response lines (e.g. AT+VER, AT+OK, AT+FFT)
            self.at_command_received_signal.emit(line)

    # ==========================================================
    #  MATRESS SIMULATOR LOGIC
    # ==========================================================

    def _simulator_loop(self):
        """
        Generates synthetic 40-sensor data representing a breathing patient.
        Includes periodic chest movements, noise aliases, and hotspot variation.
        Updates at 50Hz (20ms interval).
        """
        start_time = time.time()
        frame_count = 0
        
        # Static baseline pressure map (8x5 grid layout indices 0 to 39)
        # We define a body outline: head at center top, torso in middle, legs at bottom.
        # Grid index to spatial positions:
        # Col 0: 0-7, Col 2: 8-15, Col 1: 16-23, Col 3: 24-31, Col 4: 32-39
        # Let's assign average baselines for a standard patient laying down:
        baselines = np.zeros(40)
        
        # Torso hotspots (indices in columns 1, 2, 3 in rows 2, 3, 4)
        # Column 1: 18 (row 2), 19 (row 3), 20 (row 4)
        # Column 2: 10 (row 2), 11 (row 3), 12 (row 4)
        # Column 3: 26 (row 2), 27 (row 3), 28 (row 4)
        baselines[10] = 18000
        baselines[11] = 22000 # Max point
        baselines[12] = 15000
        
        baselines[18] = 12000
        baselines[19] = 16000
        baselines[20] = 11000
        
        baselines[26] = 14000
        baselines[27] = 19000
        baselines[28] = 13000
        
        # Head (Row 0, 1)
        baselines[9] = 8000   # Col 2, Row 1
        baselines[17] = 6000  # Col 1, Row 1
        baselines[25] = 7000  # Col 3, Row 1
        
        # Legs / Hips (Row 5, 6)
        baselines[13] = 9000
        baselines[14] = 7000
        baselines[21] = 6000
        baselines[22] = 5000
        baselines[29] = 8000
        baselines[30] = 6000

        # Modulate respiration: Chest expansion creates periodic pressure variance.
        # The main chest expansion is on sensors 11, 19, 27.
        mod_sensors = [10, 11, 12, 18, 19, 20, 26, 27, 28]
        mod_depths = np.zeros(40)
        mod_depths[11] = 1200 # Respiration amplitude
        mod_depths[19] = 800
        mod_depths[27] = 1000
        mod_depths[10] = 400
        mod_depths[12] = 300
        mod_depths[18] = 400
        mod_depths[20] = 300
        mod_depths[26] = 500
        mod_depths[28] = 400

        while self.running:
            t = time.time() - start_time
            
            # Breathing cycle: frequency = bpm / 60
            freq = self.sim_breath_rate / 60.0
            # Breathing pattern: add a slightly asymmetrical profile (deeper inhalation, passive exhalation)
            # We can model this by adding a second harmonic
            resp_signal = 0.7 * np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(4 * np.pi * freq * t - np.pi/4)
            
            frame = []
            for i in range(40):
                # Baseline
                val = baselines[i]
                
                # Respiration modulation
                val += mod_depths[i] * resp_signal * self.sim_sensitivity
                
                # Add random noise (representing optical/EMI interference)
                # Random walking high-frequency noise + tiny baseline drift
                hf_noise = np.random.normal(0, 150 * self.sim_sensitivity)
                
                # Simulating a minor AC interference (e.g. 10 Hz alias on all channels, but stronger on one)
                # Let's say sensor 15 is exceptionally noisy/susceptible to EMI
                ac_noise = 0.0
                if i == 15:
                    ac_noise = 800.0 * np.sin(2 * np.pi * 9.7 * t) # strong 9.7 Hz spike
                else:
                    ac_noise = 30.0 * np.sin(2 * np.pi * 10.0 * t)
                    
                val += hf_noise + ac_noise
                
                # Clean negative values
                val = max(0, int(val))
                frame.append(val)
                
            self.new_frame_signal.emit(frame)
            
            # Generate simulated breathing wave (AT+RWAV)
            # Make it look like a real ADC value variation
            sim_rwav = 2048.0 + 350.0 * resp_signal + np.random.normal(0, 8.0)
            self._parse_incoming_line(f"AT+RWAV {sim_rwav:.2f}")
            
            # Periodically emit AT+RR, AT+AVP to simulate hardware auto-analyses
            frame_count += 1
            if frame_count % 50 == 0: # Once per second
                self._parse_incoming_line(f"AT+RR {int(self.sim_breath_rate)}")
                self._parse_incoming_line(f"AT+AVP {int(np.mean(frame))},{int(np.ptp(frame)*0.08)}")
                
            time.sleep(0.02) # 50Hz update

    def _handle_simulated_command(self, cmd):
        """Simulates receiving commands and responding like the STM32 firmware"""
        time.sleep(0.02) # Simulate serial latency
        self.at_command_received_signal.emit(f"> {cmd}") # Echo command in console
        
        if cmd == "AT+VER":
            self.at_command_received_signal.emit(f"AT+VER {self.sim_firmware_ver}")
        elif cmd.startswith("AT+INTT"):
            # Sensitivity adjustment
            try:
                parts = cmd.split()
                if len(parts) >= 2:
                    int_val = int(parts[1])
                    self.sim_sensitivity = int_val / 100.0
                    self.at_command_received_signal.emit(f"AT+OK Sensitivity scale set to {self.sim_sensitivity:.2f}")
                else:
                    self.at_command_received_signal.emit("AT+ERROR: Invalid argument")
            except:
                self.at_command_received_signal.emit("AT+ERROR: Command parsing failed")
        elif cmd.startswith("AT+MATMOD"):
            # Mat Mode: NeoNat vs Adult
            mode = cmd.replace("AT+MATMOD", "").strip()
            if mode in ["NeoNat", "Adult"]:
                self.sim_mode = mode
                if mode == "NeoNat":
                    self.sim_breath_rate = 42.0 # Fast breathing rate for neonates
                else:
                    self.sim_breath_rate = 15.0 # Adult respiration rate
                self.at_command_received_signal.emit(f"AT+MATMOD {self.sim_mode}")
                self.connection_status_signal.emit(f"Simulator Active ({self.sim_mode} Mat Mode)", True)
            else:
                self.at_command_received_signal.emit("AT+ERROR: Choose NeoNat or Adult")
        elif cmd.startswith("AT+RRALGOSEL"):
            try:
                algo = cmd.split()[1]
                self.at_command_received_signal.emit(f"AT+OK Algorithm Selected: {algo}")
            except:
                self.at_command_received_signal.emit("AT+ERROR: Invalid index")
        elif cmd == "AT+NULLS":
            # Perform zero calibration
            self.at_command_received_signal.emit("AT+NV Calibration Saved.")
            self.at_command_received_signal.emit("AT+NULLS 0,0,0,0... Done")
        else:
            # Generic response
            self.at_command_received_signal.emit("AT+OK")
