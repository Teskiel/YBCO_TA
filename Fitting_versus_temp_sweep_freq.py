# -*- coding: utf-8 -*-
"""
Created on Thu Apr 10 16:19:37 2025

@author: Jie Hu

Purple Mountain Observatory

Email: jiehu@pmo.ac.cn

"""

import numpy as np
import matplotlib.pyplot as plt
import os

import scraps.utility as ut
import skrf as rf

import scraps.resonator as scr
from scraps.fitsS21 import cmplxIQ_fit, cmplxIQ_params

import pickle

ut.SetDefaultPlotParam()

# chip_name = "TlBCO-Meas-4th-chip"
# Meas_date = '20250512'

chip_name = "TlBCO-Meas-4th-chip-no-isolator"
Meas_date = "20250523"

meas_powers = [25]


def extract_temps(file_list,temp_indx = 0):
    
    temps = []
    for filename in file_list:
        params = ut.ExtractDatafromString(filename)
        temps.append(params[temp_indx])
        
    return temps

def sort_filelist_pairs(a_list, b_list):
    
    sorted_pairs = sorted(zip(a_list, b_list))
    a_sorted, b_sorted = zip(*sorted_pairs)
    
    # Convert back to lists if needed
    a_list = list(a_sorted)
    b_list = list(b_sorted)
    
    return a_list, b_list

def load_s_param(filename):
    
    sparams = rf.Network(filename)
    
    # fig = plt.figure()
    
    s21 = sparams.s[:,1,0]
            
    freq = sparams.f
    
    return freq, s21

def extract_s_param_seg(freq, s21, f0, span):
    
    span = 10e6;
        
    indx0 = np.argmin(np.abs(freq - f0))
        
    df = freq[1] - freq[0]
        
    count = round(span/df)
        
    indx_start = indx0 - count 
    indx_stop = indx0 + count
        
    freq_cut = freq[indx_start:indx_stop]
    s21_cut = s21[indx_start:indx_stop]
    
    return freq_cut, s21_cut

# def fit_resonance(freq, s21,)
    


# laser_powers = [0, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19]
laser_powers = [0,1, 3, 5,7, 9, 11, 13,15,17]

laser_power_meas = [0,1.144, 3.4, 5.657, 7.892, 10.17,12.44, 14.66, 16.77, 18.46, 18.461]

folder0 = '-30dBm'

s_params = []

# plt.figure()

colors,sm= ut.GenColorMap(laser_power_meas)

resfreq0s = [4.2145e9, 4.694e9, 5.5075e9]
# resfreq0s = [4.694e9]

f0s = []

for i, laser_power in enumerate(laser_powers):
    
    subfolder = '4K-%dmW-laser'%(laser_power)
    
    folder = os.path.join(folder0, subfolder)
    
    filename = os.listdir(folder)
    
    s_param_file = os.path.join(folder,filename[0])
    
    freq, s21 = load_s_param(s_param_file)
    
    s_params.append(s21)
    
    # plt.plot(freq, 20*np.log10(np.abs(s21)),color = colors[i])
    
    span = 10e6;
        
    # indx0 = np.argmin(np.abs(freq - resfreq0s[0]))
        
    # df = freq[1] - freq[0]
        
    # count = round(span/df)
        
    # indx_start = indx0 - count 
    # indx_stop = indx0 + count
        
    # freq_cut = freq[indx_start:indx_stop]
    # s21_cut = s21[indx_start:indx_stop]
    
    # res = scr.Resonator("name", 0, 0, freq_cut, np.real(s21_cut), np.imag(s21_cut))
            
    # res.load_params(cmplxIQ_params)
            
    # res.do_lmfit(cmplxIQ_fit)
        
    # plt.plot(freq_cut, 20*np.log10(np.abs(s21_cut)),color = colors[i])
    
    # plt.plot(freq_cut, 10*np.log10(np.abs(res.resultI**2 + res.resultQ**2)),'--')
    
    # f0s.append(res.f0)
    
    f0_pwr = []
    
    for resfreq0 in resfreq0s:
    
        freq_cut, s21_cut = extract_s_param_seg(freq, s21, resfreq0, span)
            
        res = scr.Resonator("name", 0, 0, freq_cut, np.real(s21_cut), np.imag(s21_cut))
            
        res.load_params(cmplxIQ_params)
            
        res.do_lmfit(cmplxIQ_fit)
        
        plt.plot(freq_cut, 20*np.log10(np.abs(s21_cut)),color = colors[i])
        
        f0_pwr.append(res.f0)
        
    f0s.append(f0_pwr)


f0s = np.array(f0s)

# plt.figure()
# plt.plot(laser_power_meas[:len(laser_powers)],f0s,'s')
plt.plot(laser_power_meas[:len(laser_powers)],(f0s[:,0] - f0s[0,0])/f0s[0,0],)
plt.plot(laser_power_meas[:len(laser_powers)],(f0s[:,1] - f0s[0,1])/f0s[0,1],)
plt.plot(laser_power_meas[:len(laser_powers)],(f0s[:,2] - f0s[0,2])/f0s[0,2],)

ps = np.array(laser_power_meas[:len(laser_powers)])

data = np.vstack([ps, f0s.T])

np.savetxt(folder0+'.txt', data.T)
    
    # if laser_power == 0:
        
    #     s_param_ref = os.path.join(folder,filename[0])
        
    # else:
        
    #     s_param_val = os.path.join(folder,filename[0])
        

    
        


# meas_power = 45

# folder0 = Meas_date +'-'+ chip_name

# foldername = Meas_date + '-' + chip_name + "-" + 'DBCO-KID-%ddBm'

# subfolder = os.path.join(folder0, 'data');

# file_list = os.listdir(subfolder)

# temps = extract_temps(file_list,temp_indx= 1);
# temps_sort, file_list_sort = sort_filelist_pairs(temps, file_list)

# indx_start = 0

# indx_max = 3000;

# freq0 = 4.58e9;

# data_processed = folder0 + '/dataprocessed/pixel 4-0'

# span = 20e6

# os.makedirs(data_processed,exist_ok=True)

# for i in range(indx_start,indx_max):

#     filename = file_list_sort[i]
    
#     temp = ut.ExtractDatafromString(filename)[1]
    
#     file_path = os.path.join(subfolder,filename)
    
#     sparams = rf.Network(file_path)
    
#     # fig = plt.figure()
    
#     s21 = sparams.s[:,1,0]
            
#     freq = sparams.f
    
#     # ax = fig.add_subplot()
#     # ax.plot(freq, 20*np.log10(np.abs(s21)))
    
#     # freq0 = 4.32e9;
    
#     # span = 40e6;
    
#     indx0 = np.argmin(np.abs(freq - freq0))
    
#     df = freq[1] - freq[0]
    
#     count = round(span/df)
    
#     indx_start = indx0 - count 
#     indx_stop = indx0 + count
    
#     freq_cut = freq[indx_start:indx_stop]
#     s21_cut = s21[indx_start:indx_stop]
    
#     res = scr.Resonator("name", 0, 0, freq_cut, np.real(s21_cut), np.imag(s21_cut))
    
#     res.load_params(cmplxIQ_params)
    
#     res.do_lmfit(cmplxIQ_fit)
    
#     # fig3 = plt.figure()
#     # ax3 = fig3.add_subplot()
#     # ax3.plot(res.INorm, res.QNorm);
#     # ax3.plot(res.resultINorm, res.resultQNorm)
    
#     fig2 = plt.figure()
#     ax2 = fig2.add_subplot()
    
#     colors = ut.ColorCombinations(3)
    
#     ax2.plot(res.freq/1e9,10*np.log10((res.INorm**2 + res.QNorm**2)),
#              linewidth = 2,label = 'Meas',color = colors[0])
#     ax2.plot(res.freq/1e9,10*np.log10((res.resultINorm**2 + res.resultQNorm**2)),
#              linewidth = 2,label = 'Fitted',color = colors[2])
    
    
#     ax2.set_xlabel("Freq(GHz)")
#     ax2.set_ylabel("$S_{21}$(dB)")
#     ax2.legend()
    
#     savefilename = os.path.join(data_processed, "%.3fGHz-S21-fitted-%.3fK-%d"%(res.f0/1e9,temp,i))
    
#     title = "Temp: %.3f K - Qi = %d"%(temp, res.Qi)
#     ax2.set_title(title)
    
    
#     fig2.savefig(savefilename + '.svg',dpi = 300,bbox_inches = 'tight')
#     fig2.savefig(savefilename + '.png',dpi = 300,bbox_inches = 'tight')
    
#     # fig2.close()
#     plt.close(fig2)
    
#     freq0 = res.f0
    
#     Q = res.Qi*res.Qc/(res.Qi + res.Qc)
    
#     span = freq0/Q*1.1
    
#     obj_filename = os.path.join(data_processed,"%.3fGHz-%.3fK-%d.obj"%(res.f0/1e9,temp,i))
#     with open(obj_filename,'wb') as f:
        
#         pickle.dump(res,f)
    

# ax2.plot(res.freq/1e9,10*np.log10((np.real(s21_cut)**2 + np.imag(s21_cut)**2)))


# for meas_power in meas_powers:

#     folder0 = Meas_date +'-'+ chip_name
    
#     foldername = Meas_date + '-' + chip_name + "-" + 'DBCO-KID-%ddBm'
    
#     subfolder = os.path.join(folder0, foldername %(meas_power));
    
#     file_list = os.listdir(subfolder)
    
#     temps = extract_temps(file_list);
    
#     indx_start = 
#     indx_max = 1800;
    
    
    
#     temps_sort, file_list_sort = sort_filelist_pairs(temps, file_list)
    
#     temps_plot = temps_sort[indx_start:indx_max][::5]
    
#     file_plot = file_list_sort[indx_start:indx_max][::5]
    
#     colors, sm = ut.GenColorMap(temps_plot,colormap = 'jet');
    
#     for i in range(len(file_plot)):
    
#         sparams = rf.Network(os.path.join(subfolder,file_plot[i]))
        
#         s21 = sparams.s[:,1,0]
        
#         freq = sparams.f

# # plt.figure(
#         ax.plot(freq/1e9, np.abs(s21),color = colors[i])

#     fig.colorbar(sm,ax = ax)
# # print(os.path.isdir(subfolder))
