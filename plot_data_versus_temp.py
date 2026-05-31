# -*- coding: utf-8 -*-
"""
Created on Thu Nov  7 18:34:16 2024

@author: Hu Jie
"""

import numpy as np

import skrf as rf

import re

import matplotlib.pyplot as plt

# import scraps.utility as ut


def get_original_indx(original_list):

    indexed_list = list(enumerate(original_list))  # [(0, 1), (1, 2), (2, 4), (3, 0), (4, 5)]
    
    # Sort by the element values (second item in each tuple)
    indexed_list.sort(key=lambda x: x[1])
    
    # Extract sorted elements and their original indices
    # sorted_elements = [element for index, element in indexed_list]
    original_indices = [index for index, element in indexed_list]
    
    return original_indices






def ExtractDatafromString(data_string):
    
    data_string = re.findall('-?\ *[0-9]+\.?[0-9]*(?:[Ee]\ *[+-]?\ *[0-9]+)?',data_string)
    
#    data_string = re.findall('-?\d\.?\d*[Ee][+\-]?\d+',data_string);
    
    data = [float(i) for i in data_string]
    
    return data
import os

folder = 'data/20250901-YBCO-Meas'

filenames = os.listdir(folder);

temps = []


for filename in filenames:
    
    
    file = folder + '/' + filename
    
    numbers = ExtractDatafromString(file)
    
    temp = numbers[1]
    
    # print(temp)
    
    
    temps.append(temp)
    
    

temp_sort = np.sort(temps)

indxs = get_original_indx(temps)

filename_sort = [filenames[x] for x in indxs]

s21s = []

# folder = r'D:/OneDrive/document/GitHub/VNAMeas'


s21_maxs = []

for filename in filename_sort:
    
    file = folder + '/' + filename
    net = rf.Network(file)
        
    s21s.append(net.s[:,1,0])    
    
    s21_maxs.append(np.max(np.abs(net.s[:,1,0])))
    
freq = net.f;

plt.figure()


for i in range(0,len(s21s)):
    
    plt.plot(freq,20*np.log10(np.abs(s21s[i])))
    


# plt.figure()
# plt.semilogx(temp_sort,20*np.log10(s21_maxs))
    
    
    



# for indx in indxs:
    
    


















    
    
    
    
