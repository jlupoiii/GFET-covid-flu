import sys
import time
import csv
import serial
from serial.tools import list_ports
import numpy as np

from PyQt5 import QtWidgets, QtCore
import pyqtgraph as pg
from PyQt5.QtWidgets import QFileDialog
from PyQt5.QtGui import QPixmap
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt5.QtCore import Qt


# -----------------------------
# CONFIG
# -----------------------------
# SERIAL_PORT = "COM6"
BAUD_RATE = 115200
N_CHANNELS = 16


class LivePlotter(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SMU Channel Plotter (pyqtgraph)")
        self.resize(1600, 800)

        # -----------------------------
        # Data buffers
        # -----------------------------
        self.x = []
        self.y = [[] for _ in range(N_CHANNELS)]
        self.sweep_running = False
        self.sweep_index = 0


        # Dirac tracking per channel
        # -----------------------------
        self.dirac_times = [[] for _ in range(N_CHANNELS)]
        self.dirac_vals  = [[] for _ in range(N_CHANNELS)]
        self.dirac_curves = []

        # -----------------------------
        # Central widget + main layout
        # -----------------------------
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QHBoxLayout(central)

        # =============================
        # LEFT: Control panel
        # =============================
        control = QtWidgets.QVBoxLayout()
        layout.addLayout(control, 0)

        start_btn = QtWidgets.QPushButton("Start Sweep")
        start_btn.setStyleSheet("background-color: green; color: white; font-weight: bold;")
        start_btn.clicked.connect(self.start_sweep)

        stop_btn = QtWidgets.QPushButton("Stop Sweep")
        stop_btn.setStyleSheet("background-color: red; color: white; font-weight: bold;")
        stop_btn.clicked.connect(self.stop_sweep)

        control.addWidget(start_btn)
        control.addWidget(stop_btn)

        # Gate voltage range
        control.addWidget(QtWidgets.QLabel("Gate Voltage Range (V)"))
        gate_layout = QtWidgets.QHBoxLayout()
        self.vmin_box = QtWidgets.QLineEdit("-0.5")
        self.vmax_box = QtWidgets.QLineEdit("1.5")
        self.vmin_box.setFixedWidth(60)
        self.vmax_box.setFixedWidth(60)
        gate_layout.addWidget(self.vmin_box)
        gate_layout.addWidget(QtWidgets.QLabel("-"))
        gate_layout.addWidget(self.vmax_box)
        control.addLayout(gate_layout)

        # Sweep delay
        control.addWidget(QtWidgets.QLabel("Sweep Delay (ms)"))
        self.sweep_delay_box = QtWidgets.QLineEdit("100")
        self.sweep_delay_box.setFixedWidth(80)
        control.addWidget(self.sweep_delay_box)

        # Channel toggles
        control.addWidget(QtWidgets.QLabel("Toggle Channels"))
        self.channel_enabled = []
        for i in range(N_CHANNELS):
            cb = QtWidgets.QCheckBox(f"Channel {i}")
            cb.setChecked(True)
            cb.stateChanged.connect(self.update_visibility)
            self.channel_enabled.append(cb)
            control.addWidget(cb)

        toggle_all = QtWidgets.QPushButton("Toggle All")
        toggle_all.clicked.connect(self.toggle_all)
        control.addWidget(toggle_all)

        # Y limits
        control.addWidget(QtWidgets.QLabel("Y Limits (µA)"))
        ylayout = QtWidgets.QHBoxLayout()
        self.ymin_box = QtWidgets.QLineEdit("0")
        self.ymax_box = QtWidgets.QLineEdit("100")
        self.ymin_box.setFixedWidth(60)
        self.ymax_box.setFixedWidth(60)
        self.ymin_box.returnPressed.connect(self.apply_ylims)
        self.ymax_box.returnPressed.connect(self.apply_ylims)
        ylayout.addWidget(self.ymin_box)
        ylayout.addWidget(QtWidgets.QLabel("-"))
        ylayout.addWidget(self.ymax_box)
        control.addLayout(ylayout)

        autoscale_btn = QtWidgets.QPushButton("Auto-scale")
        autoscale_btn.clicked.connect(self.autoscale)
        control.addWidget(autoscale_btn)

        save_btn = QtWidgets.QPushButton("Save Plot Image")
        save_btn.clicked.connect(self.save_image)
        control.addWidget(save_btn)
        control.addStretch()

        # =============================
        # MIDDLE-LEFT: Live Sweep
        # =============================
        self.plot = pg.PlotWidget()
        self.plot.setLabel("bottom", "Gate Voltage (V)")
        self.plot.setLabel("left", "Drain Current (µA)")
        self.plot.setYRange(0, 100)
        self.plot.getAxis("bottom").enableAutoSIPrefix(False)
        layout.addWidget(self.plot, 1)

        # =============================
        # MIDDLE-RIGHT: Dirac vs Time
        # =============================
        self.dirac_plot = pg.PlotWidget()
        self.dirac_plot.setLabel("bottom", "Time (s)")
        self.dirac_plot.setLabel("left", "Dirac Voltage (V)")
        self.dirac_plot.showGrid(x=True, y=True)
        layout.addWidget(self.dirac_plot, 1)

        # =============================
        # RIGHT: Legend
        # =============================
        self.legend_widget = QtWidgets.QWidget()
        self.legend_widget.setStyleSheet("background-color: black;")
        self.legend_panel = QtWidgets.QVBoxLayout(self.legend_widget)
        layout.addWidget(self.legend_widget, 0)

        label = QtWidgets.QLabel("   Legend   ")
        label.setStyleSheet("color: white; font-weight: bold;")
        self.legend_panel.addWidget(label)

        self.channel_colors = [pg.intColor(i, hues=N_CHANNELS) for i in range(N_CHANNELS)]
        self.legend_rows = []

        for i in range(N_CHANNELS):
            row = QtWidgets.QWidget()
            row_layout = QtWidgets.QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)

            lbl = QtWidgets.QLabel(f"Ch {i}")
            lbl.setStyleSheet(f"color: {self.channel_colors[i].name()}; font-weight: bold;")
            row_layout.addWidget(lbl)

            line = QtWidgets.QFrame()
            line.setFrameShape(QtWidgets.QFrame.HLine)
            line.setStyleSheet(f"background-color: {self.channel_colors[i].name()};")
            row_layout.addWidget(line, 1)

            self.legend_panel.addWidget(row)
            self.legend_rows.append(row)

        self.legend_panel.addStretch()

        # =============================
        # Curves (live sweep)
        # =============================
        self.curves = []
        for i in range(N_CHANNELS):
            curve = self.plot.plot([], [], pen=self.channel_colors[i])
            self.curves.append(curve)

        self.dirac_curves = [self.dirac_plot.plot([], [], pen=self.channel_colors[i], symbol="o",
                                                           symbolBrush=self.channel_colors[i])
                                     for i in range(N_CHANNELS)]

        # =============================
        # CSV + Serial
        # =============================

        self.csv_file = None
        self.csv_writer = None
        self.current_sweep_csv = None
        self.ser = None


###############################


    # -----------------------------
    # Sweep Functions
    # -----------------------------
    def start_sweep(self):

        # Ignore if a sweep is already running
        if self.sweep_running:
            print("Sweep already running - Start ignored")
            return


        # ------------
        # CSV setup
        # ------------
        # Close previous CSV if open
        if hasattr(self, "current_sweep_csv") and self.current_sweep_csv:
            self.current_sweep_csv.close()
            self.current_sweep_csv = None
            self.csv_writer = None
        
        # CSV for new sweeps
        if not self.setup_csv():
            print("CSV save canceled")
            return
        self.current_sweep_csv = self.csv_file

        # -----------------------------
        # Serial (keep it open if already)
        # -----------------------------
        if not self.ser or not self.ser.is_open:
            self.init_serial()


        # Clear Dirac tracking
        for ch in range(N_CHANNELS):
            self.dirac_times[ch].clear()
            self.dirac_vals[ch].clear()
            self.dirac_curves[ch].setData([], [])

        
        self.sweep_running = True    
        self.experiment_start_time = time.time()
        self.sweep_index = 0


        
        while self.sweep_running:
            # Validate gate voltage inputs
            try:
                vmin = float(self.vmin_box.text())
                vmax = float(self.vmax_box.text())
            except ValueError:
                print("Input Error", "Gate voltages must be numbers.")
    
            if vmin < -1.5 or vmax > 1.5 or vmin >= vmax:
                print("Gate voltages must satisfy:\n-1.5 ≤ min < max ≤ 1.5")

            self.plot.setXRange(vmin, vmax, padding=0)
            self.plot.enableAutoRange(axis='x', enable=False)
    
            # Validate step delay input
            try:
                sweep_delay_ms = float(self.sweep_delay_box.text())
            except ValueError:
                QtWidgets.QMessageBox.critical(
                    self, "Input Error", "Sweep delay must be a number (ms)."
                )
                return
        
            if sweep_delay_ms <= 0 or sweep_delay_ms > 5000:
                QtWidgets.QMessageBox.critical(
                    self,
                    "Input Error",
                    "Sweep delay must be between 0 and 5000 ms."
                )
                return
    
            # Clear live sweep graph and prepare x and y values
            self.x.clear()
            for ch in self.y:
                ch.clear()

    
            # -----------------------------
            # Prepare Dirac curve for this sweep
            # -----------------------------
            # Sweep start time
            self.current_sweep_start_time = time.time()


            # Send start command
            self.send_serial(f"start,{vmin},{vmax},{sweep_delay_ms}")
            sweep_completed = False
    
            # -----------------------------
            # Blocking read loop
            # -----------------------------
            while self.sweep_running:
                line = self.ser.readline().decode().strip()
                if not line:
                    continue
    
                if line == "DONE":
                    sweep_completed = True
                    break
    
                parts = line.split(",")
                if len(parts) != 19:
                    # sweep_completed = True
                    continue
    
                step = int(parts[0])
                t = float(parts[1])
                vg = float(parts[2])
                currents = list(map(float, parts[3:]))
    
                self.x.append(vg)
                for i in range(N_CHANNELS):
                    self.y[i].append(currents[i] * 1e6)
                        
    
                # write to CSV
                self.csv_writer.writerow([self.sweep_index, step, t, vg] + currents)
                self.current_sweep_csv.flush()
    
                self.update_plot()
                QtWidgets.QApplication.processEvents()

            if sweep_completed and self.sweep_running:
                # Compute Dirac points for this sweep
                self.compute_and_plot_dirac()
                self.sweep_index += 1

            # gives teensy time between sweeps to reset
            QtWidgets.QApplication.processEvents()
            time.sleep(0.05)

        print("Sweep loop exited cleanly")

    def stop_sweep(self):
        # Stop the running loop
        self.sweep_running = False

        # Close current CSV
        if self.current_sweep_csv:
            self.current_sweep_csv.close()
            self.current_sweep_csv = None
            self.csv_writer = None

        # Tell Teensy to stop sweep
        if self.ser and self.ser.is_open:
            try:
                self.ser.write(b"stop\n")
                self.ser.flush()  # ensure the command is sent
            except Exception as e:
                print("Error sending stop:", e)
            
            # Close the serial connection
            try:
                self.ser.close()
                print("Serial connection closed")
            except Exception as e:
                print("Error closing serial:", e)
        
        # Optional: clear serial object so it can be reopened later
        self.ser = None


    def compute_and_plot_dirac(self):
        """
        Compute Dirac point for each channel for the current sweep,
        append them to the tracking lists, and write a row to the CSV
        with empty strings for the sweep point data columns.
        """
        # Time since the start of the experiment (not just this sweep)
        t = time.time() - self.experiment_start_time
    
        # Compute Dirac points for all channels
        dirac_row = [""] * (4 + N_CHANNELS)  # Placeholder for SWEEP_IDX, POINT, TIME, V_GATE, I_CH0..15
        dirac_values = []
    
        for ch in range(N_CHANNELS):
            if len(self.x) < 2:
                dirac_v = ""
            else:
                y = np.array(self.y[ch])
                x = np.array(self.x)
                min_idx = np.argmin(np.abs(y))
                dirac_v = x[min_idx]
    
            # Store for tracking
            self.dirac_times[ch].append(t)
            self.dirac_vals[ch].append(dirac_v)
    
            # Update Dirac curve
            self.dirac_curves[ch].setData(self.dirac_times[ch], self.dirac_vals[ch])
    
            dirac_values.append(dirac_v)
    
        # Build the CSV row: first columns are sweep point placeholders, last columns are Dirac points
        csv_row = dirac_row + [self.sweep_index] + dirac_values
    
        # Write to CSV
        if self.current_sweep_csv:
            self.csv_writer.writerow(csv_row)
            self.current_sweep_csv.flush()
    




            


    # def init_serial(self):
    #     try:
    #         self.ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2)
    #         print("Serial connected")
    
    #         # Force Teensy reset (non-blocking, very short)
    #         self.ser.setDTR(False)
    #         time.sleep(0.05)
    #         self.ser.setDTR(True)
    
    #     except Exception as e:
    #         print(f"Serial init failed: {e}")
    #         self.ser = None
    def init_serial(self):
        try:
            port = None
            for p in list_ports.comports():
                if p.vid == 0x16C0:  # Teensy
                    port = p.device
                    break
    
            if port is None:
                raise RuntimeError("Teensy not found")
    
            self.ser = serial.Serial(port, BAUD_RATE, timeout=2)
            print(f"Serial connected on {port}")
    
            # Reset Teensy
            self.ser.setDTR(False)
            time.sleep(0.05)
            self.ser.setDTR(True)
    
        except Exception as e:
            print(f"Serial init failed: {e}")
            self.ser = None

    def send_serial(self, msg):
        if self.ser is None:
            print("Serial not initialized yet")
            return
        try:
            if self.ser.is_open:
                self.ser.write(f"{msg}\n".encode())
                self.ser.flush()  # <- ensure it sends immediately
                print(f"Sent '{msg}' through serial successfully")
        except Exception as e:
            print(f"Error sending {msg}: {e}")


    def setup_csv(self):
        dialog = QFileDialog(self, "Save CSV")
        dialog.setAcceptMode(QFileDialog.AcceptSave)
        dialog.setNameFilter("CSV Files (*.csv)")
        dialog.setOptions(QFileDialog.DontUseNativeDialog)
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowStaysOnTopHint)  # force on top
    
        if dialog.exec_() == QFileDialog.Accepted:
            path = dialog.selectedFiles()[0]
            if not path.lower().endswith(".csv"):
                path += ".csv"
        else:
            return False
    
        self.csv_file = open(path, "w", newline="")
        self.csv_writer = csv.writer(self.csv_file)
    
        header = ["SWEEP_IDX", "POINT", "TIME", "V_GATE"] \
                + [f"I_CH{i}" for i in range(N_CHANNELS)] \
                + ["DIRAC_SWEEP_IDX"] \
                + [f"DIRAC_V_CH{i}" for i in range(N_CHANNELS)]
        
        self.csv_writer.writerow(header)
        print(f"CSV file created: {path}")
        return True


    # -----------------------------
    # Plot update (FAST)
    # -----------------------------
    def update_plot(self):
        x_np = np.array(self.x)

        for i in range(N_CHANNELS):
            visible = self.channel_enabled[i].isChecked()
    
            # Live sweep
            self.curves[i].setVisible(visible)
            if visible:
                self.curves[i].setData(x_np, self.y[i])


            self.dirac_curves[i].setVisible(
                self.channel_enabled[i].isChecked()
            )

    def update_legend(self):
        # Show/hide pre-created rows based on checkbox state
        for i, row in enumerate(self.legend_rows):
            if self.channel_enabled[i].isChecked():
                row.show()
            else:
                row.hide()
            
    def toggle_all(self):
        state = not self.channel_enabled[0].isChecked()
        for cb in self.channel_enabled:
            cb.setChecked(state)

    def update_visibility(self):
        self.update_plot()
        self.update_legend()

    def apply_ylims(self):
        try:
            ymin = float(self.ymin_box.text())
            ymax = float(self.ymax_box.text())
            if ymin < ymax:
                self.plot.setYRange(ymin, ymax)
        except ValueError:
            pass

    def autoscale(self):
        """Auto-scale the axes based on the currently visible channels."""
        ymin, ymax = None, None
        # Go through all visible channels
        for i, cb in enumerate(self.channel_enabled):
            if cb.isChecked() and self.y[i]:
                data = np.array(self.y[i])
                ch_min, ch_max = data.min(), data.max()
                if ymin is None or ch_min < ymin:
                    ymin = ch_min
                if ymax is None or ch_max > ymax:
                    ymax = ch_max
    
        # If we found any data, apply limits
        if ymin is not None and ymax is not None:
            margin = 0.05 * (ymax - ymin)  # optional 5% padding
            ymin -= margin
            ymax += margin
            self.plot.setYRange(ymin, ymax)

            # Update the boxes
            self.ymin_box.setText(f"{ymin:.2f}")
            self.ymax_box.setText(f"{ymax:.2f}")


        # Validate gate voltage inputs and set the x axis
        try:
            vmin = float(self.vmin_box.text())
            vmax = float(self.vmax_box.text())
        except ValueError:
            print("Input Error", "Gate voltages must be numbers.")

        if vmin < -1.5 or vmax > 1.5 or vmin >= vmax:
            print("Gate voltages must satisfy:\n-1.5 ≤ min < max ≤ 1.5")

        self.plot.setXRange(vmin, vmax, padding=0)
        self.plot.enableAutoRange(axis='x', enable=False)

            
    def save_image(self):
        # Ask user where to save
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save Plot Image",
            "",
            "PNG Files (*.png);;JPEG Files (*.jpg);;All Files (*)"
        )
        if filename:
            # Grab the whole plot widget (with axes, labels, everything)
            pixmap = self.grab()  # grabs the whole QWidget as a QPixmap
            pixmap.save(filename)
            print(f"Saved full plot image to: {filename}")

    def closeEvent(self, event):
        print("Exiting program.")
        self.stop_sweep()
        event.accept()


        
# -----------------------------
# RUN
# -----------------------------
if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    win = LivePlotter()
    win.show()
    sys.exit(app.exec_())






