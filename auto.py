# -*- coding: utf-8 -*-
"""
MKID 自动化变温测量程序
功能：自动控制 LakeShore 335 到达指定温度，并触发 Keysight VNA 测量 Dark/Light S参数。
"""

import pyvisa
import os
import time
from Lakeshore335 import LakeShore335  # 确保你的文件夹里有这个驱动文件

# ==========================================
# 1. 配置参数
# ==========================================
VNA_ADDRESS = 'GPIB0::16::INSTR'       # Keysight VNA VISA 地址
LS_ADDRESS = 'ASRL3::INSTR'            # LakeShore 335 地址 (串口或GPIB)
SAVE_ROOT = r'C:\Users\teski\Desktop\data\20260423' # 数据存放根目录

# 想要测量的温度点 (单位: K)
TARGET_TEMPS = [4.3, 10, 20, 40,77]
# 等待温度稳定的时间 (秒)，根据你的制冷机性能调整
STABILIZE_TIME = 300 

# ==========================================
# 2. 初始化设备
# ==========================================
rm = pyvisa.ResourceManager()
vna = rm.open_resource(VNA_ADDRESS)
vna.timeout = 10000 # 10秒超时
print(f"成功连接 VNA: {vna.query('*IDN?')}")

temp_ctrl = LakeShore335(visa_address=LS_ADDRESS)
print("成功连接 LakeShore 335")

def save_vna_s2p(file_path):
    """触发 VNA 扫描并保存 s2p 文件到 PC"""
    print(f"正在采集并保存: {file_path}")
    # 切换为单次扫描并等待完成
    vna.write(":INIT:CONT OFF")
    vna.write(":INIT:IMM; *OPC?") 
    vna.read() 
    
    # 具体的保存指令因 Keysight 型号而异，这里以 PNA/ENA 常用格式为例
    # 如果是本地保存再传输，或者直接导出数据：
    vna.write(f'MMEM:STOR:TRAC:PORT 1,2,"{file_path}"') 
    # 注意：某些型号可能需要先存到VNA硬盘，再用 visa.read_raw() 传输。

# ==========================================
# 3. 主测量循环
# ==========================================
if not os.path.exists(SAVE_ROOT):
    os.makedirs(SAVE_ROOT)

try:
    for temp in TARGET_TEMPS:
        print(f"\n>>> 正在设置目标温度: {temp} K")
        # temp_ctrl.set_temperature(temp) # 假设驱动里有这个函数
        
        # 等待温度稳定
        print(f"等待 {STABILIZE_TIME} 秒确保温度稳定...")
        time.sleep(STABILIZE_TIME)
        
        # 获取当前精确温度用于命名
        current_t = temp_ctrl.get_temperature()
        print(f"当前实际温度: {current_t:.3f} K")
        
        # 创建温度文件夹
        temp_folder = os.path.join(SAVE_ROOT, f"{int(temp)}K", "data")
        if not os.path.exists(temp_folder):
            os.makedirs(temp_folder)
            
        # --- 测量 Dark ---
        input("请确认处于 DARK 状态（关闭光源/盖上盖子），按回车开始测量...")
        dark_filename = os.path.join(temp_folder, f"tlbco_dark_{current_t:.3f}K.s2p")
        save_vna_s2p(dark_filename)
        
        # --- 测量 Light ---
        input("请确认处于 LIGHT 状态（开启光源），按回车开始测量...")
        light_filename = os.path.join(temp_folder, f"tlbco_light_{current_t:.3f}K.s2p")
        save_vna_s2p(light_filename)

    print("\n✅ 所有温度点测量完成！")

finally:
    vna.close()
    # temp_ctrl.close()