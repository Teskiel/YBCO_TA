# -*- coding: utf-8 -*-
"""
Created on Fri Nov 22 10:12:58 2024

@author: heb
"""

import os
import  numpy as np
import matplotlib.pyplot as plt
import skrf as rf

folder = 'data/20241122'
files = os.listdir(folder)

plt.figure()

s11_vals = []

for file in files:

    sp = rf.Network(folder + '//' + file)
    
    
    freq = sp.f;
    
    s11 = sp.s[:,0,0] 
    
    s11_vals.append(s11[1000])
    
    plt.plot(freq, np.log10(np.abs(s11))*20)

# s11_vals = np.array(s11_vals)

# plt.plot(np.angle(s11_vals))