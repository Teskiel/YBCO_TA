
# -*- coding: utf-8 -*-

"""
Description:    Example for remote calibration with robot support to feed the calibration elements.
                Integrated with Keysight N7779C Laser control and automated power sweeping.
"""

import os
import time
from time import sleep
from RsInstrument import *
import skrf as rf
import matplotlib.pyplot as plt
import pyvisa # 新增：用于控制 Keysight 激光器

from Lakeshore335 import LakeShore335

# ---------------------------
# 仪器资源配置区
# ---------------------------
# VNA 设置
resource = 'GPIB0::20::INSTR'
# 激光器 IP 地址 (从你的浏览器截图获取)
laser_resource = 'TCPIP0::100.65.11.65::INSTR' 

# Make sure you have the last version of the RsInstrument
RsInstrument.assert_minimum_version('1.53.0')
Instrument = RsInstrument(resource, True, False, "SelectVisa='ni'")
sleep(1)

def comprep():
    """Preparation of the communication (termination, etc...)"""
    print(f'VISA Manufacturer: {Instrument.visa_manufacturer}')
    Instrument.visa_timeout = 10000
    Instrument.opc_timeout = 40000
    Instrument.instrument_status_checking = True
    Instrument.clear_status()

def close():
    """Close the VISA session"""
    Instrument.close()

def comcheck():
    """Check communication with the device"""
    idnResponse = Instrument.query_str('*IDN?')
    sleep(1)
    print('Hello, I am ' + idnResponse)

def measure():
    """Perform a single sweep measurement"""
    Instrument.write_str_with_opc('INIT1:CONTinuous OFF')
    status = Instrument.write_str_with_opc('INIT1:IMMediate')
    print('Measurement status:', status)

def saves2p(s2p_filename):
    """Save the measurement to a s2p file"""
    Instrument.write_str_with_opc(f'MMEMory:STORe:TRACe:PORTs 1, "{s2p_filename}", COMPlex, 1, 2')

def fileget(s2p_filename, pc_filename):
    """Perform calibration with short element"""
    Instrument.read_file_from_instrument_to_pc(s2p_filename, pc_filename)


# ---------------------------
# Keysight 激光器控制模块
# ---------------------------
class KeysightLaser:
    def __init__(self, resource_name):
        rm = pyvisa.ResourceManager()
        try:
            self.inst = rm.open_resource(resource_name)
            self.inst.timeout = 5000
            print("Successfully connected to Laser:", self.inst.query('*IDN?').strip())
        except Exception as e:
            print(f"Failed to connect to Laser: {e}")
            raise e

    def set_power_mw(self, power_mw):
        """设置激光器功率 (mW)"""
        # SCPI指令设置功率，单位设为MW (MilliWatts)
        self.inst.write(f':SOURce:POWer {power_mw}MW')
        
    def output_on(self):
        """打开激光输出"""
        self.inst.write(':OUTPut:STATe ON')

    def output_off(self):
        """关闭激光输出"""
        self.inst.write(':OUTPut:STATe OFF')

    def close(self):
        self.inst.close()


# ---------------------------
# 主程序开始
# ---------------------------
comprep()
comcheck()

# 初始化温度计
temp_reader = LakeShore335(visa_address= "ASRL4::INSTR")

# 初始化激光器
laser = KeysightLaser(laser_resource)

# 基础目录设定
date = "20260526"
base_folder = rf'D:\YBCO\VNAMeas\data\{date}\-45dBm'

# 你需要扫描的功率列表 (单位: mW)
power_levels = [0, 1, 3, 5, 7, 9, 11, 13, 15, 17]

count = 0

print("---------- 开始自动化测试流程 ----------")

for power in power_levels:
    
    # 1. 设置激光器功率
    print(f"\n>>> 正在准备 {power} mW 的测量环境...")
    if power == 0:
        # 0mW 时直接关闭激光输出，避免底层的合规报错
        laser.output_off()
        print("激光器输出已关闭 (0 mW)。")
    else:
        # 设置功率并开启输出
        laser.set_power_mw(power)
        laser.output_on()
        print(f"激光器已设置为 {power} mW 且输出已开启。")

    # 2. 等待3分钟 (180秒) 让系统稳定
    print("等待 3 分钟让温度/状态稳定...")
    # 可以用一个倒计时打印，避免程序看起来像卡死了
    
    # sleep(10)
    for remaining in range(180, 0, -10):
        print(f"剩余等待时间: {remaining} 秒")
        sleep(10)
        
    # # 3. 读取当前温度
    current_temp = temp_reader.get_temperature()
    print(f"当前温度: {current_temp} K")

    # 4. 自动生成类似 '4K-5mW-laser' 这样的文件夹
    # 取整数温度值构建文件夹名，如果你确定一直维持在4K附近，可将int(current_temp)替换为'4K'
    folder_data = os.path.join(base_folder, f'4K-{power}mW-laser')
    
    if not os.path.exists(folder_data):
        os.makedirs(folder_data)
        print(f"已创建新文件夹: {folder_data}")

    # 5. 定义 VNA 的本地保存路径和 PC 端的抓取路径
    s2p_filename = r'C:\2026\s2pfilename.s2p'
    pc_filename = os.path.join(folder_data, f'tlbco_in_cryostat201_small_3_6GHz_light_{count}_{current_temp:.3f}K.s2p')
    
    # 6. 执行 VNA 测量并保存
    print("开始 VNA 测量...")
    measure()
    saves2p(s2p_filename)
    fileget(s2p_filename, pc_filename)
    print(f"数据已保存至: {pc_filename}")
    
    count += 1

# 测试结束，安全关闭设备
print("\n>>> 所有功率节点测量完毕，正在关闭设备...")
laser.output_off()  # 确保结束后激光器关闭以保护设备
laser.close()
# temp_reader.close()
close() # 关闭 VNA
print('I am done')