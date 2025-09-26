# TO RUN CODE: 1) UNPLUG TEENSY
#              2) PLUG TEENSY INTO COMPUTER
#              3) MAKE SURE ARDUINO CODE IS FLASHED TO ARDUINO
#              4) RUN PYTHON SCRIPT IN BASH

import serial
import sys
import time
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import csv
import tkinter as tk
from tkinter import filedialog
from tkinter import ttk


# Setup serial connection
TEENSY_PORT = 'COM6'
BAUD_RATE = 115200
ser = serial.Serial(TEENSY_PORT, BAUD_RATE)

gate_voltage = input("Trasconductance Point (in Volts) to use as Gate Voltage: " )
try:
    gate_voltage = float(gate_voltage)
    print(f"Using {gate_voltage:.3f} V as the gate voltage")
    ser.write((str(gate_voltage) + '\n').encode('utf-8'))  # Send with newline
except ValueError:
    print(f"\"{gate_voltage}\" is not a valid gate voltage")
    sys.exit(1)


# Begin transmission, begin the loop part of arduino code
ser.write(b'start\n')


def redraw_plot(*args):
    ax.clear()
    
    # calculate max and min current for y-limits
    max_current = float('-inf')
    min_current = float('inf')
    for i in range(16):
        if channel_enabled[i].get():
            ax.plot(time_steps, [1e6*elt for elt in channel_data[i]],label=f'Channel {i}')
            if min(channel_data[i]) < min_current: 
                min_current = min(channel_data[i])
            if max(channel_data[i]) > max_current: 
                max_current = max(channel_data[i])
    if use_custom_range.get():
        try:
            custom_min = float(custom_min_entry.get())
            custom_max = float(custom_max_entry.get())
            ax.set_ylim(custom_min, custom_max)
        except ValueError:
            ax.set_ylim(min_current * 1e6, max_current * 1e6)
    else:
        ax.set_ylim(min_current * 1e6, max_current * 1e6)
    ax.set_title(f"Time vs Drain-Source Current")
    ax.set_xlabel(rf"Time ($s$)")
    ax.set_ylabel(rf"Drain-Source Current, $I_{{DS}}$ ($\mu A$)")
    ax.legend(ncol=1, fontsize='small', loc='center left', bbox_to_anchor=(1, 0.5))#, loc='upper right')
    canvas.draw()

def redraw_plot_debounced(*args):
    # used so that the plotter does not crash when the checkboxes are clicked too fast
    global redraw_after_id
    if redraw_after_id is not None:
        root.after_cancel(redraw_after_id)
    if use_custom_range.get():
        max_frame.pack(pady=2)
        min_frame.pack(pady=2)
    else:
        max_frame.pack_forget()
        min_frame.pack_forget()
    redraw_after_id = root.after(100, redraw_plot)  # redraw_plot called after 100 ms pause

def save_image():
    # Ask user where to save the image
    filename = filedialog.asksaveasfilename(
        defaultextension=".png",
        filetypes=[("PNG files", "*.png"), ("JPEG files", "*.jpg"), ("All files", "*.*")],
        title="Save current plot as..."
    )
    if filename:
        fig.savefig(filename)
        print(f"Saved current plot to: {filename}")


# Graphical User Interface Setup (GUI)
root = tk.Tk()
root.title("SMU Channel Plotter")

# left panel with checkboxes to allow for toggling channels visible / invisible
control_frame = tk.Frame(root)
control_frame.pack(side=tk.LEFT, fill=tk.Y)
tk.Label(control_frame, text="Toggle Channels").pack()
channel_enabled = [tk.BooleanVar(value=True) for _ in range(16)]
for i in range(16):
    cb = tk.Checkbutton(control_frame, text=f"Channel {i}", variable=channel_enabled[i])
    cb.pack(anchor='w')
    
# redraw plot triggered when the data collection is done
redraw_after_id = None
for i in range(16):
    channel_enabled[i].trace_add("write", lambda *_: redraw_plot_debounced())

# right panel for IV plot, for GUI
plot_frame = tk.Frame(root)
plot_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
# add button below checkboxes in the control frame, for flipping/toggling all channels
def flip_all_channels():
    for var in channel_enabled:
        var.set(not var.get())
flip_button = tk.Button(control_frame, text="Toggle All Channels", command=flip_all_channels)
flip_button.pack(pady=5)

# add button below checkboxes in the control frame, for saving the image
save_button = tk.Button(control_frame, text="Save Plot Image", command=save_image)
save_button.pack(pady=5)


# Checkbox to enable custom current range
use_custom_range = tk.BooleanVar(value=False)
custom_range_checkbox = tk.Checkbutton(control_frame, text="Custom Current Range", variable=use_custom_range, command=redraw_plot_debounced)
custom_range_checkbox.pack(pady=5)

# Entries for custom min/max current, placed beside labels
max_frame = tk.Frame(control_frame)
min_frame = tk.Frame(control_frame)

tk.Label(max_frame, text="Max (µA):").pack(side=tk.LEFT)
custom_max_entry = tk.Entry(max_frame, width=8)
custom_max_entry.pack(side=tk.LEFT)

tk.Label(min_frame, text="Min (µA):").pack(side=tk.LEFT)
custom_min_entry = tk.Entry(min_frame, width=8)
custom_min_entry.pack(side=tk.LEFT)

# Initially hidden
max_frame.pack_forget()
min_frame.pack_forget()


# End GUI setup


# set up time vs current plot
fig, ax = plt.subplots(figsize=(10, 6))
plt.subplots_adjust(right=0.8)
canvas = FigureCanvasTkAgg(fig, master=plot_frame)
canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)



# set up CSV file saving
csv_file = None
csv_writer = None
def ask_save_file_and_start():
    global csv_file, csv_writer

    # Hide main window before file dialog
    root.withdraw()
    root.update()


    save_path = filedialog.asksaveasfilename(
        defaultextension=".csv",
        filetypes=[("CSV files", "*.csv")],
        title="Save measurement data as..."
    )

    # Show the main window again after file dialog
    root.deiconify()

    if not save_path:
        print("No file selected. Data will not be saved.")
        return False

    print(f"Saving data to: {save_path}")
    csv_file = open(save_path, 'w', newline='')
    csv_writer = csv.writer(csv_file)
    header = ['POINT_NUM', 'TIMESTAMP (s)', 'V_DRAIN (V)', 'V_GATE (V)'] + [f'I_CH{i} (A)' for i in range(16)]
    csv_writer.writerow(header)
    return True




# data buffers for saving data
time_steps = []
channel_data = [[] for _ in range(16)]

# update helper function called for the animation, for reading new serial data
def update(frame):    
    global gate_voltages, channel_data, plot_deriv_button, save_image
    line = ser.readline().decode().strip()

    try:
        parts = line.split(",")
        if len(parts) != 20:
            # NEED TO MAKE CASE TO DEAL WITH MALFORMED LINES
            print("Mis-formatted serial line:")
            print(parts)
            return

        # Parse data
        step_number = int(parts[0])
        time_step = float(parts[1])
        drain_voltage = float(parts[2])
        gate_voltage = float(parts[3])
        readings = list(map(float, parts[4:]))

        # store
        time_steps.append(time_step)
        for i in range(16):
            channel_data[i].append(readings[i])

        # clear "old" plot and replot with "new" data
        ax.clear()

        # calculate max and min 
        max_current = float('-inf')
        min_current = float('inf')
        for i in range(16):
            if channel_enabled[i].get():
                ax.plot(time_steps, [1e6*elt for elt in channel_data[i]],label=f'Channel {i}')
                if min(channel_data[i]) < min_current: 
                    min_current = min(channel_data[i])
                if max(channel_data[i]) > max_current: 
                    max_current = max(channel_data[i])
        if use_custom_range.get():
            try:
                custom_min = float(custom_min_entry.get())
                custom_max = float(custom_max_entry.get())
                ax.set_ylim(custom_min, custom_max)
            except ValueError:
                ax.set_ylim(min_current * 1e6, max_current * 1e6)
        else:
            ax.set_ylim(min_current * 1e6, max_current * 1e6)
            
        ax.set_title(f"Time vs Drain-Source Current")
        ax.set_xlabel(rf"Time ($s$)")
        ax.set_ylabel(rf"Drain-Source Current, $I_{{DS}}$ ($\mu A$)")
        ax.legend(ncol=1, fontsize='small', loc='center left', bbox_to_anchor=(1, 0.5))#, loc='upper right')
        canvas.draw()
        
        # Write to CSV, written line by line as the serial data is read
        if csv_writer:
            row = [step_number, time_step, drain_voltage, gate_voltage] + readings
            csv_writer.writerow(row)
            csv_file.flush()

    except Exception as e:
        # HERE NEED TO MAKE CASE TO SKIP MALFORMED LINES
        print(f"Error parsing line: {e}")


if ask_save_file_and_start():
    ani = animation.FuncAnimation(fig, update, interval=50)
    root.mainloop()
else:
    print("Exiting because no save file was selected.")
    root.destroy()
    