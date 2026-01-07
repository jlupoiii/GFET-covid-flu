# # TO RUN CODE: 1) UNPLUG TEENSY
# #              2) PLUG TEENSY INTO COMPUTER
# #              3) MAKE SURE ARDUINO CODE IS FLASHED TO ARDUINO
# #              4) RUN PYTHON SCRIPT IN BASH

# # things to implement
# # set max and min currents based only the plots that I want to observe, regardless of 
# # 


import serial
import time
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.ticker import FuncFormatter
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import csv
import tkinter as tk
from tkinter import filedialog
import atexit
import numpy as np

ymin_axis_val = 0
ymax_axis_val = 100


def redraw_plot(*args):
    ax.clear()
    max_current = float('-inf')
    min_current = float('inf')
    for i in range(16):
        if channel_enabled[i].get():
            ax.plot(gate_voltages, [1000000*elt for elt in channel_data[i]], label=f'Channel {i}')
            if min(channel_data[i]) < min_current: 
                min_current = min(channel_data[i])
            if max(channel_data[i]) > max_current: 
                max_current = max(channel_data[i])
    ax.set_title(f"Gate Voltage vs Drain-Source Current")
    ax.set_xlabel(rf"Gate Voltage, $V_{{GS}}$ ($V$)")
    ax.set_ylabel(rf"Drain-Source Current, $I_{{DS}}$ ($\mu A$)")
    ax.set_ylim(ymin_axis_val, ymax_axis_val) # ax.set_ylim(min_current*1000000, max_current*1000000)
    ax.legend(ncol=1, fontsize='small', loc='center left', bbox_to_anchor=(1, 0.5))#, loc='upper right')
    canvas.draw()


def redraw_plot_debounced(*args):
    # used so that the plotter does not crash when the checkboxes are clicked too fast
    global redraw_after_id
    if redraw_after_id is not None:
        root.after_cancel(redraw_after_id)
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


def plot_transcondutance():
    fig_deriv, ax_deriv = plt.subplots(figsize=(10, 6))
    fig_deriv.canvas.manager.set_window_title("Transconductance Plotter")
    plotted_any = False
    transconductance_gate_voltages = []

    for i in range(16):
        if channel_enabled[i].get():
            y = np.array(channel_data[i])
            x = np.array(gate_voltages)
            dy_dx = np.gradient(y, x)

            ax_deriv.plot(x, dy_dx*1000000, label=f'dI/dV Ch {i}')
            plotted_any = True
            
            transconductance_gate_voltages.append(x[np.argmin(dy_dx)])

    if not plotted_any:
        print("no channels selected")
        return
        
    avg_transconductance_gate_voltage = np.mean(transconductance_gate_voltages)
    ax_deriv.axvline(avg_transconductance_gate_voltage, color='grey', linestyle='--')
    
    ax_deriv.set_xlabel(rf"Gate Voltage, $V_{{GS}}$ ($V$)")
    ax_deriv.set_ylabel(rf"Transconductance, $g_m$ ($\mu A/V$)")
    ax_deriv.set_title(f"Transconductance\n Average Neg Transconductance Point for Selected Channels: {avg_transconductance_gate_voltage:.3f} V")
    ax_deriv.legend(ncol=1, fontsize='small', loc='center left', bbox_to_anchor=(1, 0.5))
    plt.tight_layout()
    fig_deriv.show()


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

###############
# adding 2 text boxes for max and min y-values
# -------------------------
# Y-LIMIT CONTROL
# -------------------------
tk.Label(control_frame, text="Y Limits (µA)").pack(pady=(10, 0))

ymin_var = tk.StringVar(value="0")
ymax_var = tk.StringVar(value="100")

ymin_entry = tk.Entry(control_frame, textvariable=ymin_var, width=10)
ymax_entry = tk.Entry(control_frame, textvariable=ymax_var, width=10)

ymin_entry.pack(pady=2)
ymax_entry.pack(pady=2)

def apply_ymin(event=None):
    global ymin_axis_val

    try:
        ymin = float(ymin_var.get())
        if ymin >= ymax_axis_val:
            print("Y min must be < Y max")
            return

        ymin_axis_val = ymin
        ax.set_ylim(ymin_axis_val, ymax_axis_val)
        canvas.draw_idle()

    except ValueError:
        print("Invalid Y min input")

def apply_ymax(event=None):
    global ymax_axis_val

    try:
        ymax = float(ymax_var.get())
        if ymax <= ymin_axis_val:
            print("Y max must be > Y min")
            return

        ymax_axis_val = ymax
        ax.set_ylim(ymin_axis_val, ymax_axis_val)
        canvas.draw_idle()

    except ValueError:
        print("Invalid Y max input")

ymin_entry.bind("<Return>", apply_ymin)
ymax_entry.bind("<Return>", apply_ymax)
############


# End GUI setup


# set up IV plot
fig, ax = plt.subplots(figsize=(10, 6))

ax.set_ylim(ymin_axis_val, ymax_axis_val)
ax.set_title(f"Gate Voltage vs Drain-Source Current")
ax.set_xlabel(rf"Gate Voltage, $V_{{GS}}$ ($V$)")
ax.set_ylabel(rf"Drain-Source Current, $I_{{DS}}$ ($\mu A$)")
ax.legend(ncol=1, fontsize='small', loc='center left', bbox_to_anchor=(1, 0.5))#, loc='upper right')

plt.subplots_adjust(right=0.8)
canvas = FigureCanvasTkAgg(fig, master=plot_frame)
canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)





# set up CSV file saving
csv_file = None
csv_writer = None
def ask_save_file_and_start():
    print('asking to save file')
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
    header = ['POINT_NUM', 'TIMESTAMP (s)', 'V_GATE (V)'] + [f'I_CH{i} (A)' for i in range(16)] + [f'TRANSC_CH{i} ()' for i in range(16)]
    csv_writer.writerow(header)
    return True

# Setup serial connection
SERIAL_PORT = 'COM6'
BAUD_RATE = 115200
ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1.0)
time.sleep(2)  # Give Teensy time to reset
ser.write(b'start\n')  # Begin transmission


# # data buffers for saving data
# gate_voltages = []
# channel_data = [[] for _ in range(16)]


# # trying to make faster
# # update helper function called for the animation, for reading new serial data
# def update(frame):
#     # print('updating frame')
#     global gate_voltages, channel_data, plot_deriv_button, save_image

#     # Read one full line from serial
#     line_bytes = ser.readline()  # blocks until '\n' or timeout
#     if not line_bytes:
#         # skip if nothing received
#         return

#     line = line_bytes.decode('utf-8').strip()
#     if not line:
#         # skip if empty line
#         return


#     # case where the full sweep is complete, end the loop
#     if line == "DONE":
#         # end loop so that we don't have to pretty the teeny's button
#         ani.event_source.stop()
        
#         # adds button for allowing user to plot the transconductance point once all voltages are swept
#         plot_deriv_button = tk.Button(control_frame, text="Plot Transconductance", command=plot_transcondutance)
#         plot_deriv_button.pack(pady=10)

#         # add button below checkboxes in the control frame, for saving the image
#         save_button = tk.Button(control_frame, text="Save Plot Image", command=save_image)
#         save_button.pack(pady=5)

#     try:
#         parts = line.split(",")
#         if parts[0] == "DONE":
#             print('DONE')
#             return
#         if len(parts) != 19:
#             print("Mis-formatted serial line:")
#             print(parts)
#             return

#         # Parse data
#         step_number = int(parts[0])
#         time_step = float(parts[1])
#         # drain_voltage = float(parts[2])
#         gate_voltage = float(parts[2])
#         readings = list(map(float, parts[3:]))

#         # store
#         gate_voltages.append(gate_voltage)
#         for i in range(16):
#             channel_data[i].append(readings[i])

#         # clear "old" plot and replot with "new" data

        
#         # ax.clear()

        
#         # max_current = float('-inf')
#         # min_current = float('inf')
#         for i in range(16):
#             if channel_enabled[i].get():
#                 # ax.plot(gate_voltages, [1000000*elt for elt in channel_data[i]], label=f'Channel {i}') # prev
#                 pass
                
#                 # y_data = [elt*1e6 for elt in channel_data[i]]  # convert to uA
#                 # lines[i].set_data(gate_voltages, y_data)

#                 # # previous updating the y-limits automatically
#                 # if min(channel_data[i]) < min_current: 
#                 #     min_current = min(channel_data[i])
#                 # if max(channel_data[i]) > max_current: 
#                 #     max_current = max(channel_data[i])
#                 # if min_current == max_current:
#                 #     min_current -= 1e-9
#                 #     max_current += 1e-9
#         # if step_number % 10 == 0:
#         #     min_current = min(min(channel_data[i]) for i in range(16))
#         #     max_current = max(max(channel_data[i]) for i in range(16))
#         #     ax.set_ylim(min_current*1e6, max_current*1e6)
                    
#         # ax.set_title(f"Gate Voltage vs Drain-Source Current")
#         # ax.set_xlabel(rf"Gate Voltage, $V_{{GS}}$ ($V$)")
#         # ax.set_ylabel(rf"Drain-Source Current, $I_{{DS}}$ ($\mu A$)")
#         # # ax.set_ylim(ymin_axis_val, ymax_axis_val) # ax.set_ylim(min_current*1000000, max_current*1000000)
#         # ax.legend(ncol=1, fontsize='small', loc='center left', bbox_to_anchor=(1, 0.5))#, loc='upper right')
        
#         canvas.draw()

#         # UNCOMMENT THIS WHEN WE WANT TO RESUME TESTING
#         # # Write to CSV, written line by line as the serial data is read
#         # if csv_writer:
#         #     row = [step_number, time_step, gate_voltage] + readings
#         #     csv_writer.writerow(row)
#         #     csv_file.flush()

#     except Exception as e:
#         print(f"Error parsing line: {e}")


















# data buffers for saving data
gate_voltages = []
channel_data = [[] for _ in range(16)]

# previous, SLOW update function
# update helper function called for the animation, for reading new serial data
def update(frame):
    # print('updating frame')
    global gate_voltages, channel_data, plot_deriv_button, save_image

    # Read one full line from serial
    line_bytes = ser.readline()  # blocks until '\n' or timeout
    if not line_bytes:
        # skip if nothing received
        return

    line = line_bytes.decode('utf-8').strip()
    if not line:
        # skip if empty line
        return


    # case where the full sweep is complete, end the loop
    if line == "DONE":
        # end loop so that we don't have to pretty the teeny's button
        ani.event_source.stop()
        
        # adds button for allowing user to plot the transconductance point once all voltages are swept
        plot_deriv_button = tk.Button(control_frame, text="Plot Transconductance", command=plot_transcondutance)
        plot_deriv_button.pack(pady=10)

        # add button below checkboxes in the control frame, for saving the image
        save_button = tk.Button(control_frame, text="Save Plot Image", command=save_image)
        save_button.pack(pady=5)

    try:
        parts = line.split(",")
        if parts[0] == "DONE":
            print('DONE')
            return
        if len(parts) != 19:
            print("Mis-formatted serial line:")
            print(parts)
            return

        # Parse data
        step_number = int(parts[0])
        time_step = float(parts[1])
        # drain_voltage = float(parts[2])
        gate_voltage = float(parts[2])
        readings = list(map(float, parts[3:]))

        # store
        gate_voltages.append(gate_voltage)
        for i in range(16):
            channel_data[i].append(readings[i])

        # clear "old" plot and replot with "new" data

        
        # ax.clear()

        
        # max_current = float('-inf')
        # min_current = float('inf')
        for i in range(16):
            if channel_enabled[i].get():
                ax.plot(gate_voltages, [1000000*elt for elt in channel_data[i]], label=f'Channel {i}') # prev
                # y_data = [elt*1e6 for elt in channel_data[i]]  # convert to uA
                # lines[i].set_data(gate_voltages, y_data)

                # # previous updating the y-limits automatically
                # if min(channel_data[i]) < min_current: 
                #     min_current = min(channel_data[i])
                # if max(channel_data[i]) > max_current: 
                #     max_current = max(channel_data[i])
                # if min_current == max_current:
                #     min_current -= 1e-9
                #     max_current += 1e-9
        # if step_number % 10 == 0:
        #     min_current = min(min(channel_data[i]) for i in range(16))
        #     max_current = max(max(channel_data[i]) for i in range(16))
        #     ax.set_ylim(min_current*1e6, max_current*1e6)
                    
        # ax.set_title(f"Gate Voltage vs Drain-Source Current")
        # ax.set_xlabel(rf"Gate Voltage, $V_{{GS}}$ ($V$)")
        # ax.set_ylabel(rf"Drain-Source Current, $I_{{DS}}$ ($\mu A$)")
        # # ax.set_ylim(ymin_axis_val, ymax_axis_val) # ax.set_ylim(min_current*1000000, max_current*1000000)
        # ax.legend(ncol=1, fontsize='small', loc='center left', bbox_to_anchor=(1, 0.5))#, loc='upper right')
        
        canvas.draw()
        
        # Write to CSV, written line by line as the serial data is read
        if csv_writer:
            row = [step_number, time_step, gate_voltage] + readings
            csv_writer.writerow(row)
            csv_file.flush()

    except Exception as e:
        print(f"Error parsing line: {e}")














# ##################
# def update(frame):
#     global gate_voltages, channel_data

#     try:
#         line_bytes = ser.readline()
#         if not line_bytes:
#             return
#         line = line_bytes.decode('utf-8').strip()
#         if not line:
#             return

#         if line == "DONE":
#             ani.event_source.stop()
#             plot_deriv_button = tk.Button(control_frame, text="Plot Transconductance", command=plot_transcondutance)
#             plot_deriv_button.pack(pady=10)
#             save_button = tk.Button(control_frame, text="Save Plot Image", command=save_image)
#             save_button.pack(pady=5)
#             return

#         parts = line.split(",")
#         if len(parts) != 19:
#             print("Mis-formatted serial line:", parts)
#             return

#         # Parse data
#         step_number = int(parts[0])
#         time_step = float(parts[1])
#         gate_voltage = float(parts[2])
#         readings = list(map(float, parts[3:]))

#         # store
#         gate_voltages.append(gate_voltage)
#         for i in range(16):
#             channel_data[i].append(readings[i])

#         # Update pre-created lines
#         max_current = float('-inf')
#         min_current = float('inf')
#         for i in range(16):
#             if channel_enabled[i].get():
#                 y_data = [v*1e6 for v in channel_data[i]]  # convert to uA
#                 lines[i].set_data(gate_voltages, y_data)
#                 if len(y_data) > 0:
#                     min_current = min(min_current, min(y_data))
#                     max_current = max(max_current, max(y_data))

#         if min_current == max_current:
#             min_current -= 1e-9
#             max_current += 1e-9

#         # if 
#         ax.set_xlim(min(gate_voltages), max(gate_voltages))
#         ax.set_ylim(min_current, max_current)

#         canvas.draw()

#         # Save CSV
#         if csv_writer:
#             row = [step_number, time_step, gate_voltage] + readings
#             csv_writer.writerow(row)
#             csv_file.flush()

#     except Exception as e:
#         print(f"Error parsing line: {e}")







def poll_serial():
    update(None)
    root.after(50, poll_serial)

if ask_save_file_and_start():
    print('Made CSV save file')
    ani = animation.FuncAnimation(fig, update, interval=50)
    # poll_serial()
    root.mainloop()
else:
    print("Exiting because no save file was selected.")
    root.destroy()


