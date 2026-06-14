# -*- coding: utf-8 -*-
"""
Created on Mon Jun  8 10:34:24 2026

@author: Jie Hu

Purple Mountain Observatory

Email: jiehu@pmo.ac.cn

"""

from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
import os
import re
import dataprocess as dp

import scraps.resonator as scr
from scraps.fitsS21 import cmplxIQ_fit, cmplxIQ_params
import pickle

import scraps.utility as ut

ut.SetDefaultPlotParam()

def fit_resonance(freq, s21, resfreq, span = 20e6,temp = 0, pwr = 0):
    
    df = freq[1] - freq[0]
    index = np.argmin(np.abs(freq - resfreq))
    
    count = round(span/df)
    
    indx_start = index - count 
    indx_stop = index + count
    
    
        
    freq_cut = freq[indx_start:indx_stop]
    s21_cut = s21[indx_start:indx_stop]
    
    indx_min = np.argmin(np.abs(s21_cut))
    
    index_min_all = indx_start + indx_min;
    
    freq_cut = freq[index_min_all-count:index_min_all+count]
    s21_cut = s21[index_min_all-count:index_min_all+count]
    

    res = scr.Resonator("name", temp, pwr, freq_cut, np.real(s21_cut), np.imag(s21_cut))
            
    res.load_params(cmplxIQ_params)
            
    res.do_lmfit(cmplxIQ_fit)
    
    return res




def extract_res_and_fit(freq, s21, accepted_peaks, span = 20e6, plot_result = True):
    
    
    
    # count = round(span/df)
    
    reslist = []
    
    for peak in accepted_peaks:
        
        resfreq = peak['frequency']
        
        # index = np.argmin(np.abs(freq - resfreq))
        
        res = fit_resonance(freq, s21, resfreq, span = span)
        
        reslist.append(res)
        
        if plot_result:
            
            plt.figure()
            
            plt.plot(res.freq, 20*np.log10(np.abs(res.I**2 + res.Q**2)))
            
            plt.plot(res.freq, 10*np.log10(np.abs(res.resultI**2 + res.resultQ**2)),'--')
            
            # if savefig:
                
                
        
    return reslist




temps = range(6, 11, 2)


folder0 = "20260606_092046"

meas_powers = [25, 30, 45]
meas_laser_powers = [0, 1, 3, 5, 7, 9]

color_laser, sm2 = ut.GenColorMap(meas_laser_powers)
# ut.GenColorMap()
parent_folder = Path(folder0)

pattern = re.compile(r"^(\d+(?:\.\d+)?)K$")

temps = [
    int(float(match.group(1)))
    for subfolder in parent_folder.iterdir()
    if subfolder.is_dir()
    if (match := pattern.match(subfolder.name))
]
# print(values)
temps.sort()

temp_meas_all = []
for temp in temps:
    path_temp = os.path.join(folder0, f'{temp}K')
    if not os.path.isdir(path_temp):
        continue
    # 从第一个可用的 S2P 文件名中解析实际温度
    # 文件名格式: YBCO_-25dBm_00mW_target_6K_actual_6.123K.s2p
    found = False
    for vna_dir in sorted(os.listdir(path_temp)):
        vna_path = os.path.join(path_temp, vna_dir)
        if not os.path.isdir(vna_path):
            continue
        for laser_dir in sorted(os.listdir(vna_path)):
            laser_path = os.path.join(vna_path, laser_dir)
            if not os.path.isdir(laser_path):
                continue
            for f in os.listdir(laser_path):
                if f.endswith('.s2p'):
                    match = re.search(r"actual_([\d.]+)K", f)
                    if match:
                        temp_meas_all.append(float(match.group(1)))
                        found = True
                    break
            if found:
                break
        if found:
            break
            

s2p_file_matrix_temp = []

for indx, (temp, temp_meas) in enumerate(zip(temps, temp_meas_all)):
    
    path_temp = os.path.join(folder0, f'{temp}K')
    
    # print(path_temp)
    
    s2p_file_matrix_dBm = []
    
    for meas_power in meas_powers:
        
        path_temp_dBm = os.path.join(path_temp, f'-{meas_power}dBm')
        
        s2p_file_matrix_mW = []
        
        for meas_laser_power in meas_laser_powers:
            
            path_temp_dBm_mW = os.path.join(path_temp_dBm, f"{meas_laser_power:02d}mW")
            
            files = os.listdir(path_temp_dBm_mW)
            
            for filename in files:
                
                if ".s2p" in filename:
                    
                    s2p_path = os.path.join(path_temp_dBm_mW,filename)
                    
                    s2p_file_matrix_mW.append(s2p_path)
                    
        s2p_file_matrix_dBm.append(s2p_file_matrix_mW)
    
    
    s2p_file_matrix_temp.append(s2p_file_matrix_dBm)
        
file00_path = s2p_file_matrix_temp[0][0][0]
freq, s21 = dp.load_s_param(file00_path)

peaks, fig, ax= dp.find_true_resonances(freq=freq,
                                        s21=s21,
                                        min_prominence=3,
                                        phase_diff_prominence=None,
                                        distance=10,
                                        phase_window=10,
                                        phase_diff_snr_threshold=0.5,
                                        noise_inner_window=5,
                                        noise_outer_window=40,
                                        min_phase_diff_support_points=4,
                                        min_phase_diff_width=4,
                                        max_phase_diff_width=None,
                                        plot=True,)

resfreqs = [peak["frequency"] for peak in peaks]

pixel_indx = 1

resfreq_fit_00 = resfreqs[pixel_indx]

res_temp = resfreq_fit_00

# res_pixel_all = []

colors, sm = ut.GenColorMap(temp_meas_all)

# plt.figure()

resfreq_all = []

resfreq_fit = []

responsivit_all = []

reslist_all = []

reslist_all_p2 = []

reslist_all_p3 = []


for indx, (temp, temp_meas) in enumerate(zip(temps, temp_meas_all)):
    
    if temp_meas > 80:
        
        continue
    
    temp_files = s2p_file_matrix_temp[indx]
    
    reslist_temp = []
    
    if indx < 3:
        
        df = 0
        
    elif indx < 4:
        
        f1 = resfreq_all[indx-3]
        f2 = resfreq_all[indx-2]
        f3 = resfreq_all[indx-1]
        
        df1 = f3 - f2
        df2 = f3 - f2 - (f2 - f1)
        
        res_temp = res_temp + df1 - df2
        
    elif indx < 5:
        f1, f2, f3, f4 = resfreq_all[indx-4:indx]

        df1 = f4 - f3
        df2 = f4 - 2*f3 + f2
        df3 = f4 - 3*f3 + 3*f2 - f1
    
        res_temp = res_temp + df1 - df2 + df3
        
    else: 
        
        f1, f2, f3, f4, f5 = resfreq_all[indx-5:indx]

        df1 = f5 - f4
        df2 = f5 - 2*f4 + f3
        df3 = f5 - 3*f4 + 3*f3 - f2
        df4 = f5 - 4*f4 + 6*f3 - 4*f2 + f1
    
        res_temp = res_temp + df1 - df2 + df3 - df4
        
        
    resfreqs_vs_power = []

    for i, meas_power in enumerate(meas_powers):
        
        s2p_file_matrix_mW = temp_files[i]
        
        reslist_meas_dBm = []
        
        
        
        for j, meas_laser_power in enumerate(meas_laser_powers):
            
            file_path = s2p_file_matrix_mW[j]
            
            freq, s21 = dp.load_s_param(file_path)
            
            if temp_meas<70:
            
                res = fit_resonance(freq, s21, res_temp, temp = temp_meas, pwr = meas_power,span = 50e6)
            
            else:
                
                res = fit_resonance(freq, s21, res_temp, temp = temp_meas, pwr = meas_power,span = 50e6)
            
            reslist_meas_dBm.append(res)
            
            # folder = Path(file_path).parent.parent.parent;
            
            if i == 0 and j == 0:
                
                plt.figure()
                
                plt.plot(res.freq, 10*np.log10(res.INorm**2+res.QNorm**2),color = colors[indx])
                
                plt.title(f'temp = {temp}K')
                
                plt.plot(res.freq, 10*np.log10(res.resultINorm**2+res.resultQNorm**2),color = colors[indx],linestyle = '--')
                
                folder_save = os.path.join(folder0, 'pixel%d'%(pixel_indx))
                
                os.makedirs(folder_save,exist_ok=True)
                
                resfreq_fit.append(res.f0)
                
                reslist_all.append(res)
                
                # savefilename = os.path.join(folder_save,f'{temp_meas}K.jpg')
                # plt.savefig(savefilename,dpi = 300,bbox_inches = 'tight')
                # plt.close()
                
            if i == 1 and j == 0:
                
                reslist_all_p2.append(res)
                
            if i == 2 and j == 0:
                
               reslist_all_p3.append(res) 
        
        fig, ax = plt.subplots()
        
        for count, res in enumerate(reslist_meas_dBm):
            
            

            line = ax.plot(
                res.freq/1e9,
                10*np.log10(res.INorm**2 + res.QNorm**2),
                color=color_laser[count],
                linewidth=2,
            )
            
        ax.set_xlabel("Frequency (GHz)")
        ax.set_ylabel("$S_{21}$ (dB)")
        ax.set_title(f"T={temp_meas} K, $P_r=$-{meas_power+20} dBm")
        
        cbar = fig.colorbar(sm2, ax=ax)
        cbar.set_label("Laser Power (mW)")
            
        # print('done')
        savefilename = os.path.join(folder_save,f's21 - {temp_meas}K-{meas_power} dBm.jpg')
        
        fig.savefig(savefilename,dpi = 300, bbox_inches = 'tight')
        
        f0s = ut.ExtractLmfitParams(reslist_meas_dBm,param = 'f0')
        
        # plt.figure()
        # plt.plot(meas_laser_powers,f0s,'s')
        
        resfreqs_vs_power.append(f0s)
    
    
    plt.figure()
    
    colors_power = ut.ColorCombinations(3)
    
    df_dP = []
    for count2, f0s in enumerate(resfreqs_vs_power):
        
        f0s = np.array(f0s)
        
        plt.plot(meas_laser_powers,(f0s-f0s[0])/f0s[0]*1e6,'s',color = colors_power[count2],markersize = 6,label = f'$P_r$=-{meas_powers[count2]+20} dBm')
        
        a = np.polyfit(np.array(meas_laser_powers), f0s,1)
        
        df_dP.append(a[0])
        
    
        
    responsivit_all.append(df_dP)
        
        
    plt.xlabel('Laser power (mW)')
    plt.ylabel("$\delta f_r/f_r$ (ppm)")
    plt.title(f"T={temp_meas} K")
    plt.legend()
    
    savefilename = os.path.join(folder_save,f'res shift - {temp_meas}K.jpg')
    plt.savefig(savefilename,dpi = 300, bbox_inches = 'tight')
    plt.close()
    
    print('done')
            
        
    # resfreq_all.append(reslist_temp)
    

    res_temp = res.f0
    
    resfreq_all.append(res_temp)


resfreq_fit = np.array(resfreq_fit)

plt.figure()
plt.plot(temp_meas_all[:len(resfreq_fit)], (resfreq_fit - resfreq_fit[0])/resfreq_fit[0]*1e2,linewidth = 2, color = colors_power[0])
plt.xlabel("Temperature (K)")
plt.ylabel("$\delta f_r/f_r$ (%)")

savefilename = os.path.join(folder_save,'f0_versus_temp') 

plt.savefig(savefilename +'.jpg',dpi = 300, bbox_inches = 'tight')
plt.savefig(savefilename +'.svg',dpi = 300, bbox_inches = 'tight')





b = np.array(responsivit_all)
plt.figure()
plt.semilogx(temp_meas_all[:len(resfreq_fit)],-b[:,2]*1000,'s')
plt.xlabel("Temperature (K)")
plt.ylabel("Responsivity (Hz/W)")

savefilename = os.path.join(folder_save,f'res shift - {temp_meas}K.jpg') 
plt.savefig(savefilename,dpi = 300, bbox_inches = 'tight')


fig_s21_vs_temp, ax_s21 = plt.subplots()

color_s21_vs_temp, sm = ut.GenColorMap(temp_meas_all[:len(resfreq_fit)])

for indx, res in enumerate(reslist_all):
    
    # plt.plot(res.freq, 10*np.log10(res.INorm**2 + res.QNorm**2))
    
    
    
    # for count, res in enumerate(reslist_meas_dBm):
        
        

    ax_s21.plot( res.freq/1e9,
            10*np.log10(res.INorm**2 + res.QNorm**2),
            color=color_s21_vs_temp[indx],
            linewidth=1.5)
        
ax_s21.set_xlabel("Frequency (GHz)")
ax_s21.set_ylabel("$S_{21}$ (dB)")

cbar = fig_s21_vs_temp.colorbar(sm, ax=ax_s21)
cbar.set_label("Temperature (K)")

savefilename = os.path.join(folder_save,'s21 vs - temp') 

plt.savefig(savefilename +'.jpg',dpi = 300, bbox_inches = 'tight')
plt.savefig(savefilename +'.svg',dpi = 300, bbox_inches = 'tight')


fig_q, ax_q = plt.subplots()

color_s21_vs_temp, sm = ut.GenColorMap(temp_meas_all[:len(resfreq_fit)])


# qis = []

qis = ut.ExtractLmfitParams(reslist_all,param = 'qi')

qis2 = ut.ExtractLmfitParams(reslist_all_p2,param = 'qi')
qis3 = ut.ExtractLmfitParams(reslist_all_p3,param = 'qi')
# for indx, res in enumerate(reslist_all):
    
#     # plt.plot(res.freq, 10*np.log10(res.INorm**2 + res.QNorm**2))
    
    
    
#     # for count, res in enumerate(reslist_meas_dBm):
        
#     qis.append(res.qi)

#     ax_s21.plot( res.freq/1e9,
#             10*np.log10(res.INorm**2 + res.QNorm**2),
#             color=color_s21_vs_temp[indx],
#             linewidth=1.5)
ax_q.plot(temp_meas_all[:len(resfreq_fit)],qis,'s',color = colors_power[0])
ax_q.plot(temp_meas_all[:len(resfreq_fit)],qis2,'o',color = colors_power[0])
ax_q.plot(temp_meas_all[:len(resfreq_fit)],qis3,'d',color = colors_power[0])

ax_q.set_xlabel("Frequency (GHz)")
ax_q.set_ylabel("Qi")

# cbar = fig_s21_vs_temp.colorbar(sm, ax=ax_s21)
# cbar.set_label("Temperature (K)")

savefilename = os.path.join(folder_save,'qis_versus_temp') 

plt.savefig(savefilename +'.jpg',dpi = 300, bbox_inches = 'tight')
plt.savefig(savefilename +'.svg',dpi = 300, bbox_inches = 'tight')


    
# plt.xlabel("Freq")






            
            # peaks, fig, ax= dp.find_true_resonances(freq=freq,
            #                                         s21=s21,
            #                                         min_prominence=3,
            #                                         phase_diff_prominence=None,
            #                                         distance=10,
            #                                         phase_window=10,
            #                                         phase_diff_snr_threshold=0.5,
            #                                         noise_inner_window=5,
            #                                         noise_outer_window=40,
            #                                         min_phase_diff_support_points=4,
            #                                         min_phase_diff_width=4,
            #                                         max_phase_diff_width=None,
            #                                         plot=True,)
            
            
        #     folder = Path(file_path).parent.parent;
            
        #     filename_without_ext = Path(file_path).stem
            
        #     figname = os.path.join(folder,filename_without_ext+'.jpg')
            
        #     fig.suptitle(filename_without_ext)
            
        #     fig.savefig(figname,dpi = 300, bbox_inches = 'tight')
            
        #     plt.close(fig)
            
        #     reslist_mW = extract_res_and_fit(freq, s21, peaks, span = 20e6,plot_result=False)
            
        #     reslist_meas_dBm.append(reslist_mW)
        
        # savefolder = os.path.join(folder, 'res_versus_laser_power.obj')
        # with open(savefolder,'wb') as f:
        #     pickle.dump(reslist_meas_dBm,f)
            
        
        # with open()
        # reslist_temp.append(reslist_meas_power)
        
        
        # with open("reslist")
            
        
            # dp.find_peaks()
            






