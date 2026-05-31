# -*- coding: utf-8 -*-


"""
# GitHub examples repository path: VectorNetworkAnalyzers/Python/RsInstrument

Created 2021/05

Author:                     Jahns_P
Version Number:             1
Date of last change:        2021/06/01
Requires:                   R&S ZNB, FW 3.12 or newer and adequate options
                            Installed VISA e.g. R&S Visa 5.12.x or newer

Description:    Example for remote calibration with robot support to feed the calibration elements.


General Information:

Please always check this example script for unsuitable setting that may
destroy your DUT before connecting it to the instrument!
This example does not claim to be complete. All information has been compiled with care.
However, errors can not be ruled out.

Please find more information about RsInstrument at
https://rsinstrument.readthedocs.io/en/latest/
"""

import os
from RsInstrument import *
from time import sleep

import skrf as rf
import matplotlib.pyplot as plt

from Lakeshore335 import LakeShore335

# Define variables
# resource = 'TCPIP0::172.16.19.125::INSTR'   
resource = 'GPIB0::20::INSTR'
# VISA resource string for the device
s2p_filename = r'C:\Users\Public\Documents\Rohde-Schwarz\ZNA\Traces\s2pfile.s2p'          # Name and path of the s2p file on the instrument
pc_filename = r'D:\OneDrive\document\GitHub\VNAMeas\pcs2pfile.s2p'                                                # Name and path of the s2p file on the PC


# Make sure you have the last version of the RsInstrument
RsInstrument.assert_minimum_version('1.53.0')

# Define the device handle
# Instrument = RsInstrument(resource)
# Instrument = RsInstrument(resource, True, False, "Sel")
Instrument = RsInstrument(resource, True, False, "SelectVisa='ni'")

"""
(resource, True, True, "SelectVisa='rs'") has the following meaning:
(VISA-resource, id_query, reset, options)
- id_query: if True: the instrument's model name is verified against the models 
supported by the driver and eventually throws an exception.   
- reset: Resets the instrument (sends *RST) command and clears its status syb-system
- option SelectVisa:
            - 'SelectVisa = 'socket' - uses no VISA implementation for socket connections - you do not need any VISA-C installation
            - 'SelectVisa = 'rs' - forces usage of Rohde&Schwarz Visa
            - 'SelectVisa = 'ni' - forces usage of National Instruments Visa     
"""
sleep(1)                                                                              # Eventually add some waiting time when reset is performed during initialization


def comprep():
    """Preparation of the communication (termination, etc...)"""
    print(f'VISA Manufacturer: {Instrument.visa_manufacturer}')     # Confirm VISA package to be chosen
    Instrument.visa_timeout = 5000                                  # Timeout for VISA Read Operations
    Instrument.opc_timeout = 20000                                   # Timeout for opc-synchronised operations
    Instrument.instrument_status_checking = True                    # Error check after each command, can be True or False
    Instrument.clear_status()                                       # Clear status register


def close():
    """Close the VISA session"""
    Instrument.close()


def comcheck():
    """Check communication with the device"""

    # Just knock on the door to see if instrument is present
    idnResponse = Instrument.query_str('*IDN?')
    sleep(1)
    print('Hello, I am ' + idnResponse)


def measure():
    """Perform a single sweep measurement"""
    Instrument.write_str_with_opc('INIT1:CONTinuous OFF')
    status = Instrument.write_str_with_opc('INIT1:IMMediate')
    print(status)


def saves2p(s2p_filename):
    """Save the measurement to a s2p file"""
    # Instrument.write_str_with_opc("CALC:PAR:SEL 'TR")
    Instrument.write_str_with_opc(f'MMEMory:STORe:TRACe:PORTs 1, "{s2p_filename}", COMPlex, 1, 2')
    # An S2P file does only contain real and imaginary part of each scatter parameter of the measurement.
    # To extract e.g. the magnitude and phase data of each trace, better use the command
    # MMEMory:STORe:TRACe:CHANnel 1, 'tracefile.csv', FORM, LINPhase
    # Using this simple file format it will be stored in path
    # C:\Users\Public\Documents\Rohde-Schwarz\Vna


def fileget(s2p_filename, pc_filename):
    """Perform calibration with short element"""
    Instrument.read_file_from_instrument_to_pc(s2p_filename, pc_filename)


# ---------------------------
# Main Program begins here
# just calling the functions
# ---------------------------

comprep()
comcheck()
# meassetup()
# measure()
# saves2p()
# fileget()

# temp_reader = LakeShore335(gpib_address=12)
# temp_reader  = LakeShore335(visa_address= "ASRL3::INSTR")

# current_temp = temp_reader.get_temperature()

current_temp = 250

print(current_temp)

count_max = 1

date = "202604016"

count = 0

while count<count_max:
    
    # s2p_filename = r'C:\Users\Public\Documents\Rohde-Schwarz\ZNA\Traces\s2pfilename.s2p'
    s2p_filename = r'C:\2026\s2pfilename.s2p'
    
    folder = r'D:\YBCO\VNAMeas\data\%s'%(date)
    
    if os.path.isdir(folder) is False:
        
        os.makedirs(folder)
    
    
    folder_data = os.path.join(folder, 'data-9')
    
    if os.path.isdir(folder_data) is False:
        
        os.makedirs(folder_data)
        
    
    
    pc_filename = folder_data + '\\tlbco_in_cryostat201_small_3_6GHz_dark_%d_%.3fK.s2p'%(count,current_temp)                                              # Name and path of the s2p file on the PC

    
    
    count = count + 1;
    
    measure()
    
    saves2p(s2p_filename)
    fileget(s2p_filename,pc_filename)
    
    sleep(5)
    
    current_temp = temp_reader.get_temperature()
    
    print(count)

# # temp_reader.close()
# # net = rf.Network(pc_filename)

# # net.plot_s_db()
# close()

# print('I am done')