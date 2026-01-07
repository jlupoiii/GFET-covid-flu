import sys
import time
import csv
import serial
import numpy as np

from PyQt5 import QtWidgets, QtCore
import pyqtgraph as pg
# from pyqtgraph.exporters import ImageExporter
from PyQt5.QtWidgets import QFileDialog
from PyQt5.QtGui import QPixmap
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

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

        # -----------------------------
        # Central widget
        # -----------------------------
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QHBoxLayout(central)

        # -----------------------------
        # Control panel (left)
        # -----------------------------
        control = QtWidgets.QVBoxLayout()
        layout.addLayout(control, 0)

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

        # Auto-scale Y-axis button
        autoscale_btn = QtWidgets.QPushButton("Auto Y-scale")
        autoscale_btn.clicked.connect(self.autoscale_y)
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
        self.setup_csv()

        # -----------------------------
        # Serial
        # -----------------------------
        self.ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        time.sleep(2)
        self.ser.write(b"start\n")

        # -----------------------------
        # Timer (poll serial)
        # -----------------------------
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.read_serial)
        self.timer.start(10)  # fast polling

    # -----------------------------
    # CSV
    # -----------------------------
    def setup_csv(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save CSV",
            "",
            "CSV Files (*.csv)"
        )
        if not path:
            sys.exit(0)

        self.csv_file = open(path, "w", newline="")
        self.csv_writer = csv.writer(self.csv_file)

        header = (
            ["POINT", "TIME", "V_GATE"]
            + [f"I_CH{i}" for i in range(N_CHANNELS)]
        )
        self.csv_writer.writerow(header)

    # -----------------------------
    # Serial read
    # -----------------------------
    def read_serial(self):
        try:
            line = self.ser.readline().decode().strip()
            if not line:
                return

            if line == "DONE":
                self.timer.stop()
                return

            parts = line.split(",")
            if len(parts) != 19:
                return

            step = int(parts[0])
            t = float(parts[1])
            vg = float(parts[2])
            currents = list(map(float, parts[3:]))

            self.x.append(vg)
            for i in range(N_CHANNELS):
                self.y[i].append(currents[i] * 1e6)

            # CSV write
            self.csv_writer.writerow([step, t, vg] + currents)
            self.csv_file.flush()

            self.update_plot()

        except Exception as e:
            print("Serial error:", e)

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

    def autoscale_y(self):
        """Auto-scale the Y-axis based on the currently visible channels."""
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
