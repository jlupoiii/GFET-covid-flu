import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit


class DataSweep():
    def __init__(self, filename):
        self.data = {}
        raw_data = np.loadtxt('data/'+filename).T
        self.data['voltages'] = raw_data[0,:]
        self.data['num_devices'] = raw_data.shape[0] - 1

        for i in range(self.data['num_devices']):
            self.data[str(i)] = raw_data[i+1, :]

        # plt.scatter(self.data['voltages'], self.data['1'], marker='o')
        # plt.xlabel("Voltage (V)")
        # plt.ylabel("Resistance (Ohms)")
        # plt.show()

    def dirac_voltages(self):
        dirac_voltages = {}
        for dev_num in range(self.data['num_devices']):
            dev_num = str(dev_num)
            dirac_voltages[dev_num] = self.data['voltages'][np.argmax(self.data[dev_num])]
        return dirac_voltages

    def transconductance_voltages(self):
        voltage_derivatives = {}
        for dev_num in range(self.data['num_devices']):
            dev_num = str(dev_num)
            voltage_derivatives[dev_num] = [self.data[dev_num][i] - self.data[dev_num][i+1] for i in range(len(self.data[dev_num])-1)]
            
            # plt.scatter(self.data['voltages'][:-1], voltage_derivatives[dev_num], marker='o')
            # plt.xlabel("Voltage (V)")
            # plt.ylabel("Resistance Change (Delta Ohms)")
            # plt.show()

        transconductance_voltages = {}
        for dev_num in range(self.data['num_devices']):
            dev_num = str(dev_num)
            transconductance_voltages[dev_num + '+'] = self.data['voltages'][np.argmax(voltage_derivatives[dev_num])]
            transconductance_voltages[dev_num + '-'] = self.data['voltages'][np.argmin(voltage_derivatives[dev_num])]
        return transconductance_voltages


    def transconductance_conductances(self):
        voltage_derivatives = {}
        for dev_num in range(self.data['num_devices']):
            dev_num = str(dev_num)
            voltage_derivatives[dev_num] = [self.data[dev_num][i] - self.data[dev_num][i+1] for i in range(len(self.data[dev_num])-1)]

        transconductance_conductances = {}
        for dev_num in range(self.data['num_devices']):
            dev_num = str(dev_num)
            transconductance_conductances[dev_num + '+'] = 1 / (self.data[dev_num][np.argmax(voltage_derivatives[dev_num])])
            transconductance_conductances[dev_num + '-'] = 1 / (self.data[dev_num][np.argmin(voltage_derivatives[dev_num])])

        return transconductance_conductances
        


def hill_function(x, A, K, n):
    return A * (x**n) / (K**n + x**n)

def downward_hill_function(x, A, K, n):
    return A * (1 - (x**n) / (K**n + x**n))
            
        

    