# -*- coding: utf-8 -*-
"""
Created on Thu Nov  7 10:35:08 2024

@author: Jie Hu

Purple Mountain Observatory

Email: jiehu@pmo.ac.cn

"""

# import pyvisa 


import pyvisa
import time
from pyvisa.constants import Parity, StopBits

class LakeShore335:
    def __init__(self, gpib_address=12, resource_manager=None,visa_address = None):
        """
        Initialize the Lake Shore 335 controller.

        :param gpib_address: GPIB address of the device (default: 12).
        :param resource_manager: Optional pyvisa ResourceManager instance.
        """
        self.gpib_address = gpib_address
        self.resource_manager = resource_manager or pyvisa.ResourceManager()
        
        
        
        # try:
            # self.device = self.resource_manager.open_resource(f'GPIB::{self.gpib_address}::INSTR')
        
        # except:
            # ASRL3::INSTR
        self.device = self.resource_manager.open_resource(visa_address)
        
        if "ASRL" in visa_address:
            
            self.device.baud_rate = 57600;
            self.device.data_bits = 7;
            self.device.parity = Parity.odd;
            self.device.stop_bits = StopBits.one
            
            # self.device.flow_control = FlowControl.none
            
            self.device.timeout = 2000
            
            self.device.read_termination = "\n"
            self.device.write_termination = "\n"
        
        
        # Verify connection
        # self.device.clear()
        # time.sleep(0.1)
        string = self.device.query("*IDN?")
        print("Connected to:", string)

    def set_temperature(self, setpoint, loop=1, wait = False,  heater_range = 0, channel = 1, wait_time = 120):
        """
        Set the temperature setpoint for a specific control loop.
        
        :param setpoint: Target temperature in Kelvin.
        :param loop: Control loop to set the temperature for (default: 1).
        
        :heater_range, 0 off, 1, low , 2, medium, 3, high
        
        """
        self.device.write(f"SETP {loop},{setpoint}")
        
        count = 0;
        
        if wait == True: #the heater will be turn on to 
            
        
            self.set_heater_range(channel,heater_range)
            
            time.sleep(2)
            
            percent = self.get_heater_percent(channel)
            
            # print(percent)
            
            if percent == 0.0:
                
                self.set_heater_range(channel,heater_range)
                
                print("range error!")
        
            if percent > 90 and heater_range < 3:
                
                self.set_heater_range(channel,heater_range+1)
                
                range_changed = 1
                
            else:
                
                range_changed = 0;
                
            
                
                
            time.sleep(wait_time)
            
            t_real = self.get_temperature();
            
            while abs(setpoint - t_real)>0.05:
                
                time.sleep(1)
                count = count+1;
                
                if count > wait_time:
                    
                    break
                
                    return 0, range_changed;
                
            return 1, range_changed;
                
            
                
                
                
        
        
        

    def get_temperature(self, channel='A'):
        """
        Get the current temperature reading from a specific channel.

        :param channel: Channel to read the temperature from ('A' or 'B').
        :return: Current temperature in Kelvin.
        """
        response = self.device.query(f"KRDG? {channel}\r")
        return float(response)

    def set_heater_range(self, channel, range_level):
        """
        Set the heater output range.

        :param range_level: Heater range (0 = Off, 1 = Low, 2 = Medium, 3 = High).
        """
        self.device.write(f"RANGE {channel}, {range_level}\r")

    def get_heater_percent(self, channel = 1):
        """
        Get the current heater output in percentage.
        
        :return: Heater output in percentage.
        """
        response = self.device.query("HTR? %d\r"%(channel))
        
        return float(response)
    
    def set_pid(self, p, i, d, loop=1):
        """
        Set PID parameters for a control loop.
    
        Lake Shore 335 command:
            PID <output>,<P>,<I>,<D>
    
        :param p: Proportional gain
        :param i: Integral value
        :param d: Derivative value
        :param loop: Control output / loop number, usually 1 or 2
        """
        self.device.write(f"PID {loop},{p},{i},{d}")

    def get_pid(self, loop=1):
        """
        Get PID parameters for a control loop.
    
        Lake Shore 335 query:
            PID? <output>
    
        :param loop: Control output / loop number, usually 1 or 2
        :return: tuple (p, i, d)
        """
        response = self.device.query(f"PID? {loop}")
        values = response.strip().split(",")
    
        if len(values) != 3:
            raise RuntimeError(f"Unexpected PID response: {response!r}")
    
        p, i, d = map(float, values)
        return p, i, d
    
    def print_pid(self, loop=1):
        """
        Print current PID parameters.
        """
        p, i, d = self.get_pid(loop)
        print(f"Loop {loop} PID: P={p}, I={i}, D={d}")
    
    def set_p(self, p, loop=1):
        """
        Change only P while keeping current I and D.
        """
        _, i, d = self.get_pid(loop)
        self.set_pid(p, i, d, loop)
    
    def set_i(self, i, loop=1):
        """
        Change only I while keeping current P and D.
        """
        p, _, d = self.get_pid(loop)
        self.set_pid(p, i, d, loop)
    
    def set_d(self, d, loop=1):
        """
        Change only D while keeping current P and I.
        """
        p, i, _ = self.get_pid(loop)
        self.set_pid(p, i, d, loop)
    
    def set_pid_and_verify(self, p, i, d, loop=1, tolerance=1e-6):
        """
        Set PID and read it back to verify.
    
        :return: True if readback matches within tolerance, otherwise False
        """
        self.set_pid(p, i, d, loop)
        time.sleep(0.1)
    
        p_read, i_read, d_read = self.get_pid(loop)
    
        ok = (
            abs(p_read - p) <= tolerance and
            abs(i_read - i) <= tolerance and
            abs(d_read - d) <= tolerance
        )
    
        if not ok:
            print(
                f"PID verify failed. "
                f"Set: P={p}, I={i}, D={d}; "
                f"Read: P={p_read}, I={i_read}, D={d_read}"
            )
    
        return ok
        

    

    def close(self):
        """Close the connection to the device."""
        self.device.close()

# Example usage:
# controller = LakeShore335(gpib_address=12)
# controller.set_temperature(4.2)  # Set temperature to 4.2 K
# temp = controller.get_temperature()
# print("Current temperature:", temp)
# controller.set_heater_range(1)  # Set heater to Low range
# heater_output = controller.get_heater_output()
# print("Heater output:", heater_output)
# controller.close()


# address = "ASRL3::INSTR"

# a = LakeShore335(visa_address=address)

# print(a.get_heater_percent())

# print(a.get_temperature())

# a.close()








# from lakeshore import Model335, Model335InputSensorSettings

# # Connect to the first available Model 335 temperature controller over USB using a baud rate of 57600
# my_model_335 = Model335(57600)

# # Create a new instance of the input sensor settings class
# # sensor_settings = Model335InputSensorSettings(my_model_335.InputSensorType.DIODE, True, False,
# #                                               my_model_335.InputSensorUnits.KELVIN,
# #                                               my_model_335.DiodeRange.TWO_POINT_FIVE_VOLTS)

# # # Apply these settings to input A of the instrument
# # my_model_335.set_input_sensor("A", sensor_settings)

# # # Set diode excitation current on channel A to 10uA
# # my_model_335.set_diode_excitation_current("A", my_model_335.DiodeCurrent.TEN_MICROAMPS)

# # # Collect instrument data
# # heater_output_1 = my_model_335.get_heater_output(1)
# # heater_output_2 = my_model_335.get_heater_output(2)
# temperature_reading = my_model_335.get_all_kelvin_reading()


# # Open a csv file to write
# # file = open("335_record_data.csv", "w")

# # Write the data to the file
# # file.write("Data retrieved from the Lake Shore Model 335\n")
# # file.write("Temperature Reading A: " + str(temperature_reading[0]) + "\n")
# # file.write("Temperature Reading B: " + str(temperature_reading[1]) + "\n")
# # file.write("Heater Output 1: " + str(heater_output_1) + "\n")
# # file.write("Heater Output 2: " + str(heater_output_2) + "\n")
# # file.close()