import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
import math
import random
from matplotlib.ticker import ScalarFormatter, FuncFormatter

class Dataset():
    def __init__(self, filenames, apt_filename, id_filename):
        '''
        This Dataset class serves to process data for GFET data, for a single data well, including
        multiple devices per well, over the gate voltage sweeps for multiple concentrations.
        
        Parameters:
            filenames: list of filenames that contains gate voltage sweeps, each for a single concentration
            apt_filename: the filename of the voltage sweep for the devices with only the aptamer
        Returns:
            None

        Format of each file:
            First column: gate voltage
            All other columns: Drain-Source Resistance for a single device. Each row shows the resistance
            experienced by each device for the gate voltage of the 1st column.

        This assumes that all of the aptamer data along with ALL concentrations share the same gate voltage steps.
        The initial dirac voltage does not have to have the same gate voltage steps.
        '''
        # initialize raw data and the data's basic features
        self.num_concs = len(filenames) # number of concentrations tested
        self.num_devices = 0 # number of devices in the well at hand, set super high to start it will get smaller later
        self.voltages = [] # list of the voltages we sweep over
        for conc in range(self.num_concs): # calcluate the voltages list, number of voltages, and number of devices
            raw_data = np.loadtxt('data/'+filenames[conc])[:, [0, 1, 2, 3, 5]].T # [:, [0, 1, 2, 4]] # ONLY HERE BECAUSE WE WANT TO IGNORE FET 3
            if len(raw_data[0,:]) > len(self.voltages): 
                self.voltages = raw_data[0,:] # gets the biggest list of voltages to sweep over (some stop at 1.5V and others at 1.4V, we want 1.5)
            self.num_devices = raw_data.shape[0] - 1

        # builds resistance info
        self.apt_resistances = {} # dictionary of lists of aptemer resistances. {device_number: resistance_list}
        self.id_resistances = {} # dictionary of lists of initial dirac resistances. {device_number: resistance_list}
        for dev_num in range(self.num_devices):
            raw_data_apt = np.loadtxt('data/'+apt_filename)[:, [0, 1, 2, 3, 5]].T  # ONLY HERE BECAUSE WE WANT TO IGNORE FET 4
            raw_data_id = np.loadtxt('data/'+id_filename)[:, [0, 1, 2, 3, 5]].T  # ONLY HERE BECAUSE WE WANT TO IGNORE FET 4
            self.apt_resistances[dev_num] = raw_data_apt[dev_num+1]
            self.id_resistances[dev_num] = raw_data_id[dev_num+1]
            self.id_voltages = raw_data_id[0]
            
        self.resistances = {}  # dictionary of dictionary of resistance list. {concentration_num: {device_number: list_of_resistances}}
        for conc in range(self.num_concs):
            conc_data_dic = {}
            for dev_num in range(self.num_devices):
                raw_data = np.loadtxt('data/'+filenames[conc])[:, [0, 1, 2, 3, 5]].T # [:, [0, 1, 2, 4]] # ONLY HERE BECAUSE WE WANT TO IGNORE FET 3
                conc_data_dic[dev_num] = raw_data[dev_num+1]
            self.resistances[conc] = conc_data_dic

        # builds resistance derivative info
        self.resistance_derivatives = {} # dictionary of dictionary of delta resistance list. {concentration_num: {device_number: list_of_resistance_changes}}
        for conc in range(self.num_concs):
            conc_resistance_derivative = {}
            for dev_num in range(self.num_devices): 
                conc_resistance_derivative[dev_num] = [self.resistances[conc][dev_num][i] - self.resistances[conc][dev_num][i+1] for i in range(len(self.resistances[conc][dev_num])-1)]
            self.resistance_derivatives[conc] = conc_resistance_derivative
        self.apt_resistance_derivatives = {} # dictionary of lists of aptemer delta resistance. {device_number: list_of_resistance_changes}
        self.id_resistance_derivatives = {} # dictionary that has the same structure as apt_resistance_derivatives, but for initial dirac sweep
        for dev_num in range(self.num_devices): 
            self.apt_resistance_derivatives[dev_num] = [self.apt_resistances[dev_num][i] - self.apt_resistances[dev_num][i+1] for i in range(len(self.apt_resistances[dev_num])-1)]
            self.id_resistance_derivatives[dev_num] = [self.id_resistances[dev_num][i] - self.id_resistances[dev_num][i+1] for i in range(len(self.id_resistances[dev_num])-1)]

        # builds dirac voltage info
        self.apt_dirac_voltages = {} # dictionary of lists for dirac voltages for the aptemer. The list enumerates the concentrations. {device_number: dirac_voltage_list}
        self.id_dirac_voltages = {} # dictionary that has the same structure as apt_dirac_voltages, but for initial dirac sweep
        for dev_num in range(self.num_devices):
            self.apt_dirac_voltages[dev_num] = self.voltages[np.argmax(self.apt_resistances[dev_num])]
            self.id_dirac_voltages[dev_num] = self.id_voltages[np.argmax(self.id_resistances[dev_num])]
        self.dirac_voltages = np.zeros((self.num_concs, self.num_devices)) # 2D array of dirac voltages. x:concentration, y: device_number
        self.adj_dirac_voltages = np.zeros((self.num_concs, self.num_devices)) # 2D array of dirac voltage shifts (adjusted). x:concentration, y: device_number
        for conc in range(self.num_concs):
            for dev_num in range(self.num_devices):
                self.dirac_voltages[conc,dev_num] = self.voltages[np.argmax(self.resistances[conc][dev_num])]
                self.adj_dirac_voltages[conc,dev_num] = self.voltages[np.argmax(self.resistances[conc][dev_num])] - self.apt_dirac_voltages[dev_num]

        # builds info about transconductance voltages, both pos and neg
        self.apt_pos_transc_voltages = {} # dictionary of lists for positive transconductance voltages for the aptemer. The list enumerates the concentrations. {device_number: pos_transc_v_list}
        self.apt_neg_transc_voltages = {}# dictionary of lists for negative transconductance voltages for the aptemer. The list enumerates the concentrations. {device_number: neg_transc_v_list}
        for dev_num in range(self.num_devices):
                self.apt_pos_transc_voltages[dev_num] = self.voltages[np.argmax(self.apt_resistance_derivatives[dev_num])]
                self.apt_neg_transc_voltages[dev_num] = self.voltages[np.argmin(self.apt_resistance_derivatives[dev_num])]
        self.pos_transc_voltages = np.zeros((self.num_concs, self.num_devices)) # 2D array of positive transconductance voltages. x:concentration, y: device_number
        self.neg_transc_voltages = np.zeros((self.num_concs, self.num_devices)) # 2D array of negative transconductance voltages. x:concentration, y: device_number
        self.adj_pos_transc_voltages = np.zeros((self.num_concs, self.num_devices)) # 2D array of positive transconductance voltage shifts (adjusted). x:concentration, y: device_number
        self.adj_neg_transc_voltages = np.zeros((self.num_concs, self.num_devices)) # 2D array of negative transconductance voltage shifts (adjusted). x:concentration, y: device_number
        for conc in range(self.num_concs):
            for dev_num in range(self.num_devices):
                self.pos_transc_voltages[conc, dev_num] = self.voltages[np.argmax(self.resistance_derivatives[conc][dev_num])]
                self.neg_transc_voltages[conc, dev_num] = self.voltages[np.argmin(self.resistance_derivatives[conc][dev_num])]
                self.adj_pos_transc_voltages[conc, dev_num] = self.voltages[np.argmax(self.resistance_derivatives[conc][dev_num])] - self.apt_pos_transc_voltages[dev_num]
                self.adj_neg_transc_voltages[conc, dev_num] = self.voltages[np.argmin(self.resistance_derivatives[conc][dev_num])] - self.apt_neg_transc_voltages[dev_num]

        # builds info about conductances
        self.apt_conductances = {dev_num: 1/self.apt_resistances[dev_num] for dev_num in range(self.num_devices)} # dictionary of lists of conductances for the aptamer readings. {device_number: conductance_list}
        self.id_conductances = {dev_num: 1/self.id_resistances[dev_num] for dev_num in range(self.num_devices)} # dictionary that has the same structure as apt_conductances, but for initial dirac sweep
        self.conductances = {} # dictionary of dictionaries of lists for conductance readings. {concentration: {device_number: conductance_list}}
        for conc in range(self.num_concs):
            self.conductances[conc] = [1 / self.resistances[conc][dev_num] for dev_num in range(self.num_devices)]

        # builds info about conductance derivatives
        self.conductance_derivatives = {} # dictionary of dictionary of delta conductance list. {concentration_num: {device_number: list_of_conductance_changes}}
        for conc in range(self.num_concs):
            conc_conductance_derivative = {}
            for dev_num in range(self.num_devices): 
                conc_conductance_derivative[dev_num] = [self.conductances[conc][dev_num][i] - self.conductances[conc][dev_num][i+1] for i in range(len(self.conductances[conc][dev_num])-1)]
            self.conductance_derivatives[conc] = conc_conductance_derivative
        self.apt_conductance_derivatives = {} # dictionary of lists of aptemer delta conductance. {device_number: list_of_conductance_changes}
        self.id_conductance_derivatives = {} # dictionary that has the same structure as apt_conductance_derivatives, but for initial dirac sweep
        for dev_num in range(self.num_devices): 
            self.apt_conductance_derivatives[dev_num] = [self.apt_conductances[dev_num][i] - self.apt_conductances[dev_num][i+1] for i in range(len(self.apt_conductances[dev_num])-1)]
            self.id_conductance_derivatives[dev_num] = [self.id_conductances[dev_num][i] - self.id_conductances[dev_num][i+1] for i in range(len(self.id_conductances[dev_num])-1)]

        # builds info about normalized dirac voltages
        self.norm_dirac_voltages = np.zeros((self.num_concs, self.num_devices)) # 2D array of normalized dirac voltages. x:concentration, y:device_number
        for dev_num in range(self.num_devices):
            self.norm_dirac_voltages[:,dev_num] = (self.adj_dirac_voltages[:,dev_num] - self.apt_dirac_voltages[dev_num]) / self.apt_dirac_voltages[dev_num]

    
    def conductance_shifts(self, voltage_to_track):
        '''
        Calculates the conductance shift over different concentrations, for a static gate voltage.

        Returns:
            2D array of conductance shifts, x: concentration, y: device_number
        Paramerers:
            voltage_to_track: gate voltage to fix, must be in the list self.voltages
        '''
        voltage_idx = np.abs(self.voltages - voltage_to_track).argmin() # index of voltage we want to track in self.voltages. The voltage can be an average of others so it may not be on the list

        # builds the 2D array of conductances at a voltage
        conductance_at_voltage = np.zeros((self.num_concs, self.num_devices)) # 2D array of conductances. x:concentration, y: device_number
        for conc in range(self.num_concs):
            for dev_num in range(self.num_devices):
                conductance_at_voltage[conc, dev_num] = self.conductances[conc][dev_num][voltage_idx]

        # builds the 2D array of the change in conductances at a voltage. This change is with respect to the aptamer conductance
        delta_conductance = np.zeros((self.num_concs, self.num_devices)) # 2D list tracking the change in conductances. x:concentration, y: device_number
        for dev_num in range(self.num_devices):
            delta_conductance[:,dev_num] = conductance_at_voltage[:,dev_num] - self.apt_conductances[dev_num][voltage_idx]

        return delta_conductance

    
    def normalized_conductance_shifts(self, voltage_to_track):
        '''
        Calculates the normalized conductance shift over different concentrations, for a specific gate voltage.
        Normalization strategy is
                (I_0-I) / I_0 , 
        where I_0 is the aptamer coductance

        Returns:
            2D array of normalized conductance shifts, x: concentration, y: device_number
        Paramerers:
            voltage_to_track: gate voltage to fix, must be in the list self.voltages
        
        '''
        delta_G = self.conductance_shifts(voltage_to_track) # un-normalized conductance shift

        voltage_idx = np.abs(self.voltages - voltage_to_track).argmin() # index of voltage we want to track in self.voltages

        # builds G_0 list
        G_0 = {} # aptamer conductance, 
        for dev_num in range(self.num_devices):
            G_0[dev_num] = self.apt_conductances[dev_num][voltage_idx]

        # builds G_norm array
        G_norm = np.zeros((self.num_concs, self.num_devices))
        for dev_num in range(self.num_devices):
            # G_norm[:,dev_num] = (G_0[dev_num] - delta_G[:,dev_num]) / G_0[dev_num]
            G_norm[:,dev_num] = (delta_G[:,dev_num] - G_0[dev_num]) / G_0[dev_num]

        return G_norm

    def analysis(self, data_array_2D):
        '''
        Performs curve fitting of a data array vs concentration. For example, Dirac Voltage vs concentration, or conductance vs concentration.

        Returns:
            concentrations_list: The list of concentrations that corresponds to the data_array_flattened list. Neeed because the data_array_2D was flattened
            data_array_flattened: The flattened list from data_array_2D, needed because pyplot cannot plot 2D matrices.
            hill_coeffs = (A, K, n, b): Coefficients for hill curve fitted to distribution
            std_devs: The list, as long as the number of concentrations, for the standard deviations at each concentration
        Parameters:
            data_array_2D: 2D array of data we want to use. Must have x: concentration, y: device_number
        '''
        concentrations_list = np.repeat(range(self.num_concs), self.num_devices) # The list of concentrations that corresponds to the data_array_flattened list. Neeed because the data_array_2D is flattened
        data_array_flattened = data_array_2D.flatten() # The flattened list from data_array_2D, needed because pyplot cannot plot 2D matrices.
        hill_coeffs, c = curve_fit(hill_function, concentrations_list, data_array_flattened) # fits the datapoints to hill_function, the hill curve
        std_devs = [] # calculates the standard deviation for each concentration
        for i in range(self.num_concs):
            mu = hill_function(i, *hill_coeffs)
            val = np.sqrt(1/self.num_devices * sum([(mu - x_j)**2 for x_j in data_array_flattened[i*self.num_devices:i*(self.num_devices+1)]]))
            std_devs.append(val)
            
        # calculates slope, which is needed for LOD
        inf_point_x = inflection_point_hill_function(*hill_coeffs)
        slope = derivative_hill_function(inf_point_x, *hill_coeffs)
        print('inf point', inf_point_x)

        # calculates standard deviation at low concentration, which is needed for lOD 
        conc_to_take_std_dev = 3
        std_dev = np.std(data_array_flattened[conc_to_take_std_dev*self.num_devices:conc_to_take_std_dev*(self.num_devices+1)])

        # caluclates and prints LOD, LOQ, and dynamic range
        LOD = 3.3 * std_dev / slope
        LOQ = 10 * std_dev / slope
        print(f'sensitivity: {slope}') # :.4f}')
        print(f'LOD: {LOD} for decade, but for real:', str(10**(-18 + LOD)))
        print(f'Theoetical dynamic range: {LOD} to {999999}')
        print(f'Experimental dynamic range: {LOD} to 10^-9')
        print(f'LOQ: {LOQ}')
        print(f'Dynamic range: {LOD} to {LOQ}')
        
        return concentrations_list, data_array_flattened, hill_coeffs, std_devs


    def dirac_analysis(self):
        '''
        Analysis for dirac voltage shift
        '''
        return self.analysis(self.adj_dirac_voltages)

    def dirac_analysis_normalized(self):
        '''
        Analysis for normalized dirac voltage shift
        '''
        return self.analysis(self.norm_dirac_voltages)
        
    def pos_transc_conduc_analysis(self):
        '''
        Analysis for transconductance conductance, at the mean of the positive transconductance point
        '''
        avg_pos_apt_transc_voltage = np.mean(list(self.apt_pos_transc_voltages.values()))        
        return self.analysis(self.conductance_shifts(avg_pos_apt_transc_voltage))

    def pos_transc_conduc_analysis_normalized(self):
        '''
        Analysis for normalzied transconductance conductance, at the mean of the positive transconductance point
        '''
        avg_pos_apt_transc_voltage = np.mean(list(self.apt_pos_transc_voltages.values()))
        return self.analysis(self.normalized_conductance_shifts(avg_pos_apt_transc_voltage))
        
    def neg_transc_conduc_analysis(self):
        '''
        Analysis for transconductance conductance, at the mean of the negative transconductance point
        '''
        avg_neg_apt_transc_voltage = np.mean(list(self.apt_neg_transc_voltages.values()))        
        return self.analysis(self.conductance_shifts(avg_neg_apt_transc_voltage))

    def neg_transc_conduc_analysis_normalized(self):
        '''
        Analysis for normalized transconductance conductance, at the mean of the negative transconductance point
        '''
        avg_neg_apt_transc_voltage = np.mean(list(self.apt_neg_transc_voltages.values()))
        return self.analysis(self.normalized_conductance_shifts(avg_neg_apt_transc_voltage))

def hill_function(x, A, K, n, b):
    '''
    Hill curve
    Returns the value at input x, given coefficients
    '''
    if K < 0: K=random.uniform(0, 5) # setting arbitrary K value if K<0 because this throws error. Done because polyfit
    return A * (x**n) / (K**n + x**n) + b

def derivative_hill_function(x, A, K, n, b):
    '''
    Derivative of the hill curve
    Returns the value at input x, given coefficients
    '''
    return A * n * K**n * (x**(n-1)) / (K**n + x**n)**2

def inflection_point_hill_function(A, K, n, b):
    '''
    The inflection point of the hill curve
    Returns the inflection point, given coefficients
    '''
    return K* ((n-1)/(n+1))**(1/n)

# def downward_hill_function(x, A, K, n, b):
#     return A * (1 - (x**n) / (K**n + x**n)) + b

# def inverse_hill_function(y, A, K, n, b):
#     return np.power(((y - b) * K**n) / (A - (y - b)), 1/n)

def format_with_e(x, pos):
    '''
    Used in pyplot, for formatting the y-axis so that the numbers use e notation, not leading 0's or e's above the y-axis
    '''
    return f'{x:.1e}' if not x==0 else 0
            
        

    