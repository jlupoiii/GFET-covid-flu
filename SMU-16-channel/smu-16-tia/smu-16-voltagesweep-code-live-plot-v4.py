import sys
import time
import csv
import serial
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
SERIAL_PORT = "COM6"
BAUD_RATE = 115200
N_CHANNELS = 16

# -----------------------------
# MAIN APP
# -----------------------------
class LivePlotter(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SMU Channel Plotter (pyqtgraph)")
        self.resize(1400, 700)  # wider to fit legend outside

        # -----------------------------
        # Data buffers (grow dynamically)
        # -----------------------------
        self.x = []
        self.y = [[] for _ in range(N_CHANNELS)]

        self.sweep_running = False

        # -----------------------------
        # Central widget
        # -----------------------------
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QHBoxLayout(central)

        # -----------------------------
        # Control panel (left)
        # -----------------------------

        # start and stop buttons
        control = QtWidgets.QVBoxLayout()
        layout.addLayout(control, 0)

        start_btn = QtWidgets.QPushButton("Start Sweep")
        start_btn.setStyleSheet("background-color: green; color: white; font-weight: bold;")

        stop_btn = QtWidgets.QPushButton("Stop Sweep")
        stop_btn.setStyleSheet("background-color: red; color: white; font-weight: bold;")

        start_btn.clicked.connect(self.start_sweep)
        stop_btn.clicked.connect(self.stop_sweep)
        
        control.addWidget(start_btn)
        control.addWidget(stop_btn)
        

        # button for setting voltage values for gate voltage
        control.addWidget(QtWidgets.QLabel("Gate Voltage Range (V)"))
        
        gate_range_layout = QtWidgets.QHBoxLayout()
        
        self.vmin_box = QtWidgets.QLineEdit("-0.5")  # default min
        self.vmax_box = QtWidgets.QLineEdit("1.5")   # default max
        
        self.vmin_box.setFixedWidth(60)
        self.vmax_box.setFixedWidth(60)
        
        gate_range_layout.addWidget(self.vmin_box)
        gate_range_layout.addWidget(QtWidgets.QLabel("-"))
        gate_range_layout.addWidget(self.vmax_box)
        
        control.addLayout(gate_range_layout)


        # Sweep delay input button, step delay
        control.addWidget(QtWidgets.QLabel("Sweep Delay (ms)"))
        
        self.sweep_delay_box = QtWidgets.QLineEdit("100")  # default 100 ms
        self.sweep_delay_box.setFixedWidth(80)
        control.addWidget(self.sweep_delay_box)

        
        # Toggle channel buttons
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

        
        # Widget for Y-limits
        control.addWidget(QtWidgets.QLabel("Y Limits (µA)"))
        
        ylayout = QtWidgets.QHBoxLayout()
        
        self.ymin_box = QtWidgets.QLineEdit("0")
        self.ymax_box = QtWidgets.QLineEdit("100")
        
        self.ymin_box.setFixedWidth(60)  # optional: make boxes smaller
        self.ymax_box.setFixedWidth(60)
        
        self.ymin_box.returnPressed.connect(self.apply_ylims)
        self.ymax_box.returnPressed.connect(self.apply_ylims)
        
        ylayout.addWidget(self.ymin_box)
        ylayout.addWidget(QtWidgets.QLabel("-"))
        ylayout.addWidget(self.ymax_box)
        
        control.addLayout(ylayout)

        # Auto-scale button
        autoscale_btn = QtWidgets.QPushButton("Auto-scale")
        autoscale_btn.clicked.connect(self.autoscale)
        control.addWidget(autoscale_btn)

        
        # Widget for saving plot image
        save_btn = QtWidgets.QPushButton("Save Plot Image")
        save_btn.clicked.connect(self.save_image)
        control.addWidget(save_btn)
        
        transconduct_btn = QtWidgets.QPushButton("Plot Transconductance")
        transconduct_btn.clicked.connect(self.plot_transconductance)
        control.addWidget(transconduct_btn)

        control.addStretch()

        # -----------------------------
        # Plot widget (middle)
        # -----------------------------
        self.plot = pg.PlotWidget()
        layout.addWidget(self.plot, 1)

        self.plot.setLabel("bottom", "Gate Voltage (V)")
        self.plot.setLabel("left", "Drain Current (µA)")
        self.plot.setYRange(0, 100)

        # Disable automatic SI prefix scaling
        self.plot.getAxis('bottom').setStyle(showValues=True)
        self.plot.getAxis('bottom').enableAutoSIPrefix(False)

        # -----------------------------
        # Legend panel (right)
        # -----------------------------
        self.legend_widget = QtWidgets.QWidget()
        self.legend_widget.setStyleSheet("background-color: black;")
        self.legend_panel = QtWidgets.QVBoxLayout(self.legend_widget)
        layout.addWidget(self.legend_widget, 0)
        
        # Add title
        label = QtWidgets.QLabel("   Legend   ")
        label.setStyleSheet("color: white; font-weight: bold;")
        self.legend_panel.addWidget(label)
        
        # Fixed colors for each channel
        self.channel_colors = [pg.intColor(i, hues=N_CHANNELS) for i in range(N_CHANNELS)]
        
        # Pre-create all 16 legend rows (placeholders)
        self.legend_rows = []
        for i in range(N_CHANNELS):
            row = QtWidgets.QWidget()
            row_layout = QtWidgets.QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            
            # Channel label
            lbl = QtWidgets.QLabel(f"Ch {i}")
            lbl.setStyleSheet(f"color: {self.channel_colors[i].name()}; font-weight: bold;")
            row_layout.addWidget(lbl)
            
            # Colored line
            line = QtWidgets.QFrame()
            line.setFrameShape(QtWidgets.QFrame.HLine)
            line.setFrameShadow(QtWidgets.QFrame.Sunken)
            line.setLineWidth(2)
            line.setStyleSheet(f"color: {self.channel_colors[i].name()}; background-color: {self.channel_colors[i].name()};")
            row_layout.addWidget(line, 1)
            
            self.legend_panel.addWidget(row)
            self.legend_rows.append(row)
        
        # Add stretch at the bottom
        self.legend_panel.addStretch()


        # -----------------------------
        # Curves (pre-created)
        # -----------------------------
        self.curves = []
        for i in range(N_CHANNELS):
            curve = self.plot.plot(
                [], [],
                pen=self.channel_colors[i],  # use fixed color # pg.intColor(i),
                name=f"Ch {i}"
            )
            self.curves.append(curve)

        

        # -----------------------------
        # CSV setup
        # -----------------------------
        self.csv_file = None
        self.csv_writer = None

        # -----------------------------
        # Serial
        # -----------------------------
        self.ser = None  # placeholder

    def init_serial(self):
        try:
            self.ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2)
            print("Serial connected")
    
            # Force Teensy reset (non-blocking, very short)
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

    def start_sweep(self):

        # Validate gate voltage inputs
        try:
            vmin = float(self.vmin_box.text())
            vmax = float(self.vmax_box.text())
        except ValueError:
            QtWidgets.QMessageBox.critical(
                self, "Input Error", "Gate voltages must be numbers."
            )
            return

        if vmin < -1.5 or vmax > 1.5 or vmin >= vmax:
            QtWidgets.QMessageBox.critical(
                self,
                "Input Error",
                "Gate voltages must satisfy:\n-1.5 ≤ min < max ≤ 1.5",
            )
            return

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

        
        # Clear data
        self.x.clear()
        for ch in self.y:
            ch.clear()
        for curve in self.curves:
            curve.setData([], [])

        # setup csv
        if self.csv_file:
            self.csv_file.close()
            self.csv_file = None
            self.csv_writer = None
        if not self.setup_csv():
            # exit out of window if X'd out or canceled  out of CSV save window
            print("CSV save canceled, sweep not started")
            return
    
        # Close previous serial if open
        if self.ser and self.ser.is_open:
            self.ser.close()
    
        # Open serial fresh (timeout=2s like before)
        self.ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2)
        self.ser.setDTR(False)
        time.sleep(0.05)
        self.ser.setDTR(True)
        time.sleep(0.5)
    
        # Send start command
        self.send_serial(f"start,{vmin},{vmax},{sweep_delay_ms}")


        self.sweep_running = True
    
        # Blocking read loop (GUI stays responsive with processEvents)
        while self.sweep_running:
            line = self.ser.readline().decode().strip()
            if not line:
                continue
    
            if line == "DONE":
                self.stop_sweep()
                break
    
            parts = line.split(",")
            if len(parts) != 19:
                continue
    
            step = int(parts[0])
            t = float(parts[1])
            vg = float(parts[2])
            currents = list(map(float, parts[3:]))
    
            self.x.append(vg)
            for i in range(N_CHANNELS):
                self.y[i].append(currents[i] * 1e6)

            # write to current csv sweep
            self.csv_writer.writerow([step, t, vg] + currents)
            self.csv_file.flush()
    
            self.update_plot()
            QtWidgets.QApplication.processEvents()  # keeps GUI responsive



    def stop_sweep(self):
        # Stop the running loop
        self.sweep_running = False

        # Close CSV for this sweep
        if self.csv_file:
            self.csv_file.close()
            self.csv_file = None
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

    def closeEvent(self, event):
        self.stop_sweep()
        event.accept()
            
    # -----------------------------
    # CSV
    # -----------------------------
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
    
        header = ["POINT", "TIME", "V_GATE"] + [f"I_CH{i}" for i in range(N_CHANNELS)]
        self.csv_writer.writerow(header)
        print(f"CSV file created: {path}")
        return True


    # -----------------------------
    # Plot update (FAST)
    # -----------------------------
    def update_plot(self):
        x_np = np.array(self.x)

        for i in range(N_CHANNELS):
            if self.channel_enabled[i].isChecked():
                self.curves[i].setData(x_np, self.y[i])
            else:
                self.curves[i].setData([], [])

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
            # self.plot.setYRange(ymin, ymax)
            self.plot.enableAutoRange()
            # Update the boxes
            self.ymin_box.setText(f"{ymin:.2f}")
            self.ymax_box.setText(f"{ymax:.2f}")

            
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
            
    def plot_transconductance(self):
        """Open a new window showing the transconductance (dI/dV) of selected channels."""
        # Check if any channels are selected
        plotted_any = False
        transconductance_gate_voltages = []
    
        # Create a new window
        win = QtWidgets.QWidget()
        win.setWindowTitle("Transconductance Plotter")
        layout = QtWidgets.QVBoxLayout(win)
    
        # Create matplotlib figure and canvas
        fig = Figure(figsize=(10, 6))
        canvas = FigureCanvas(fig)
        layout.addWidget(canvas)
        ax = fig.add_subplot(111)
    
        # Compute and plot dI/dV for each selected channel
        x = np.array(self.x)
        for i, cb in enumerate(self.channel_enabled):
            if cb.isChecked() and self.y[i]:
                y = np.array(self.y[i])
                dy_dx = np.gradient(y, x)  # derivative
                ax.plot(x, dy_dx, color=self.channel_colors[i].getRgbF()[:3], label=f'dI/dV Ch {i}')
                plotted_any = True
                # Example: store gate voltage of minimum derivative
                transconductance_gate_voltages.append(x[np.argmin(dy_dx)])
    
        if not plotted_any:
            print("No channels selected")
            return
    
        # Average "critical point" (optional vertical line)
        avg_point = np.mean(transconductance_gate_voltages)
        ax.axvline(avg_point, color='grey', linestyle='--')
    
        ax.set_xlabel("Gate Voltage (V)")
        ax.set_ylabel("Transconductance, dI/dV (µA/V)")
        ax.set_title(f"Transconductance\nAverage Neg Transconductance Point: {avg_point:.3f} V")
        ax.legend(ncol=1, fontsize='small', loc='center left', bbox_to_anchor=(1, 0.5))
        fig.tight_layout()
    
        # -----------------------------
        # Add a save button
        # -----------------------------
        save_btn = QtWidgets.QPushButton("Save Transconductance Plot")
        layout.addWidget(save_btn)
    
        def save_transconductance():
            filename, _ = QFileDialog.getSaveFileName(
                win,
                "Save Transconductance Plot",
                "",
                "PNG Files (*.png);;JPEG Files (*.jpg);;All Files (*)"
            )
            if filename:
                # Save the entire window as a QPixmap (includes button)
                pixmap = win.grab()
                pixmap.save(filename)
                print(f"Saved transconductance window to: {filename}")
    
        save_btn.clicked.connect(save_transconductance)
    
        # Show the window
        win.show()

        


# -----------------------------
# RUN
# -----------------------------
if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    win = LivePlotter()
    win.show()
    sys.exit(app.exec_())
