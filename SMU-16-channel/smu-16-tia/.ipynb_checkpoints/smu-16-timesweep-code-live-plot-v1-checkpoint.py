import sys
import time
import csv
import serial
import numpy as np

from PyQt5 import QtWidgets
import pyqtgraph as pg
from PyQt5.QtWidgets import QFileDialog
from PyQt5.QtCore import Qt


# -----------------------------
# CONFIG
# -----------------------------
SERIAL_PORT = "COM6"
BAUD_RATE = 115200
N_CHANNELS = 16
MAX_POINTS = 4000 # the max number of points displayed at one time


class LivePlotter(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SMU Time Sweep Plotter")
        self.resize(1600, 800)

        # -----------------------------
        # Data buffers
        # -----------------------------
        self.t = []
        self.y = [[] for _ in range(N_CHANNELS)]
        self.dy_dt = [[] for _ in range(N_CHANNELS)]
        self.point_idx = 0
        self.sweep_running = False

        # -----------------------------
        # Central widget + layout
        # -----------------------------
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QHBoxLayout(central)

        # =============================
        # LEFT: Controls
        # =============================
        control = QtWidgets.QVBoxLayout()
        layout.addLayout(control, 0)

        start_btn = QtWidgets.QPushButton("Start")
        start_btn.setStyleSheet("background-color: green; color: white; font-weight: bold;")
        start_btn.clicked.connect(self.start_sweep)

        stop_btn = QtWidgets.QPushButton("Stop")
        stop_btn.setStyleSheet("background-color: red; color: white; font-weight: bold;")
        stop_btn.clicked.connect(self.stop_sweep)

        control.addWidget(start_btn)
        control.addWidget(stop_btn)

        control.addWidget(QtWidgets.QLabel("Gate Voltage (V)"))
        self.gate_box = QtWidgets.QLineEdit("-0.3")
        self.gate_box.setFixedWidth(80)
        control.addWidget(self.gate_box)

        control.addWidget(QtWidgets.QLabel("Sample Delay (ms)"))
        self.delay_box = QtWidgets.QLineEdit("100")
        self.delay_box.setFixedWidth(80)
        control.addWidget(self.delay_box)

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

        control.addStretch()

        # =============================
        # MIDDLE-LEFT: I vs Time
        # =============================
        self.plot = pg.PlotWidget()
        self.plot.setLabel("bottom", "Time (s)")
        self.plot.setLabel("left", "Drain Current (µA)")
        self.plot.showGrid(x=True, y=True)
        layout.addWidget(self.plot, 1)

        # =============================
        # MIDDLE-RIGHT: dI/dt vs Time
        # =============================
        self.deriv_plot = pg.PlotWidget()
        self.deriv_plot.setLabel("bottom", "Time (s)")
        self.deriv_plot.setLabel("left", "dI/dt (µA/s)")
        self.deriv_plot.showGrid(x=True, y=True)
        layout.addWidget(self.deriv_plot, 1)

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
        # Curves
        # =============================
        # self.channel_colors = [pg.intColor(i, hues=N_CHANNELS) for i in range(N_CHANNELS)]

        self.curves = []
        self.deriv_curves = []

        for i in range(N_CHANNELS):
            self.curves.append(self.plot.plot([], [], pen=self.channel_colors[i]))
            self.deriv_curves.append(self.deriv_plot.plot([], [], pen=self.channel_colors[i]))

        # =============================
        # CSV + Serial
        # =============================
        self.csv_file = None
        self.csv_writer = None
        self.ser = None

    # -----------------------------
    # Start sweep
    # -----------------------------
    def start_sweep(self):
        # Ignore if a sweep is already running
        if self.sweep_running:
            print("Sweep already running - Start ignored")
            return
        
        # if csv not saving, then do not start sweep
        if not self.setup_csv():
            return

        
        if not self.ser or not self.ser.is_open:
            self.init_serial()

        # validate gate voltage input
        try:
            gate_v = float(self.gate_box.text())
        except ValueError:
            print("Input Error", "Gate voltage must be a number.")

        if gate_v < -1.5 or gate_v > 1.5:
            print("Gate voltage must satisfy:\n-1.5 ≤ gate_v ≤ 1.5")


        # Validate step delay input
        try:
            delay_ms = float(self.delay_box.text())
        except ValueError:
            QtWidgets.QMessageBox.critical(
                self, "Input Error", "Sweep delay must be a number (ms)."
            )
            return
        if delay_ms <= 0 or delay_ms > 5000:
            QtWidgets.QMessageBox.critical(
                self,
                "Input Error",
                "Sweep delay must be between 0 and 5000 ms."
            )
            return
        

        self.t.clear()
        for ch in range(N_CHANNELS):
            self.y[ch].clear()
            self.dy_dt[ch].clear()

        self.sweep_running = True
        self.point_idx = 0


        # Send Arduino command
        self.send_serial(f"start,{gate_v},{delay_ms}")
        

        while self.sweep_running:
            line = self.ser.readline().decode().strip()
            if not line:
                continue

            parts = line.split(",")
            if len(parts) != 1 + N_CHANNELS:
                continue

            t = float(parts[0])
            currents = np.array(parts[1:], dtype=float) * 1e6

            self.t.append(t)

            for ch in range(N_CHANNELS):
                self.y[ch].append(currents[ch])

                if len(self.t) >= 2:
                    dt = self.t[-1] - self.t[-2]
                    di = self.y[ch][-1] - self.y[ch][-2]
                    self.dy_dt[ch].append(di / dt if dt > 0 else 0)
                else:
                    self.dy_dt[ch].append(0)

            # self.csv_writer.writerow([t] + currents.tolist())
            # self.csv_file.flush()
            self.csv_writer.writerow(
                [self.point_idx, t, gate_v]
                + currents.tolist()
                + [self.dy_dt[ch][-1] for ch in range(N_CHANNELS)]
            )
            self.csv_file.flush()
            
            self.point_idx += 1




            # Sliding window
            if len(self.t) > MAX_POINTS:
                self.t = self.t[-MAX_POINTS:]
                for ch in range(N_CHANNELS):
                    self.y[ch] = self.y[ch][-MAX_POINTS:]
                    self.dy_dt[ch] = self.dy_dt[ch][-MAX_POINTS:]
            

            self.update_plot()
            QtWidgets.QApplication.processEvents()

    # -----------------------------
    # Stop sweep
    # -----------------------------
    def stop_sweep(self):
        self.sweep_running = False

        if self.ser and self.ser.is_open:
            try:
                self.ser.write(b"stop\n")
                self.ser.flush()
                self.ser.close()
            except Exception as e:
                print("Serial stop error:", e)

        self.ser = None

        if self.csv_file:
            self.csv_file.close()
            self.csv_file = None
            self.csv_writer = None

    # -----------------------------
    # Plot update
    # -----------------------------
    def update_plot(self):
        t_np = np.array(self.t)

        for i in range(N_CHANNELS):
            visible = self.channel_enabled[i].isChecked()
            self.curves[i].setVisible(visible)
            self.deriv_curves[i].setVisible(visible)

            if visible:
                self.curves[i].setData(t_np, self.y[i])
                self.deriv_curves[i].setData(t_np, self.dy_dt[i])

    def update_legend(self):
        # Show/hide pre-created rows based on checkbox state
        for i, row in enumerate(self.legend_rows):
            if self.channel_enabled[i].isChecked():
                row.show()
            else:
                row.hide()

    def update_visibility(self):
        self.update_plot()
        self.update_legend()

    def toggle_all(self):
        state = not self.channel_enabled[0].isChecked()
        for cb in self.channel_enabled:
            cb.setChecked(state)

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
            # margin = 0.05 * (ymax - ymin)  # optional 5% padding
            margin=0
            ymin -= margin
            ymax += margin
            self.plot.setYRange(ymin, ymax)

            # Update the boxes
            self.ymin_box.setText(f"{ymin:.2f}")
            self.ymax_box.setText(f"{ymax:.2f}")

        self.plot.enableAutoRange(axis='x', enable=True)
        self.plot.enableAutoRange(axis='y', enable=True)
        

        # for deriv plot, auto scale for both x and y
        self.deriv_plot.enableAutoRange(axis='x', enable=True)
        self.deriv_plot.enableAutoRange(axis='y', enable=True)


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
            

    # -----------------------------
    # Serial helpers
    # -----------------------------
    def init_serial(self):
        try:
            self.ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2)
            self.ser.setDTR(False)
            time.sleep(0.05)
            self.ser.setDTR(True)
            print("Serial connected")
        except Exception as e:
            print("Serial init failed:", e)
            self.ser = None

    # def send_serial(self, msg):
    #     if self.ser and self.ser.is_open:
    #         self.ser.write(f"{msg}\n".encode())
    #         self.ser.flush()
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

    # -----------------------------
    # CSV
    # -----------------------------
    def setup_csv(self):
        dialog = QFileDialog(self, "Save CSV")
        dialog.setAcceptMode(QFileDialog.AcceptSave)
        dialog.setNameFilter("CSV Files (*.csv)")
        dialog.setOptions(QFileDialog.DontUseNativeDialog)

        if dialog.exec_() != QFileDialog.Accepted:
            return False

        path = dialog.selectedFiles()[0]
        if not path.lower().endswith(".csv"):
            path += ".csv"

        self.csv_file = open(path, "w", newline="")
        self.csv_writer = csv.writer(self.csv_file)

        # header = ["TIME"] + [f"I_CH{i}" for i in range(N_CHANNELS)]
        header = ["POINT_IDX", "TIME", "V_GATE"] \
                + [f"I_CH{i}" for i in range(N_CHANNELS)] \
                + [f"DI/DT{i}" for i in range(N_CHANNELS)]
        self.csv_writer.writerow(header)
        return True

    # -----------------------------
    # Close
    # -----------------------------
    def closeEvent(self, event):
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
