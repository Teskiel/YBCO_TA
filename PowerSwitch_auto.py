# -*- coding: utf-8 -*-

"""
Description:    Example for measuring transient S-parameter response when switching 
                between two laser power levels.
                Records 20 continuous measurements and calculates the average interval.
"""

import os
import time
from time import sleep
from RsInstrument import *
import skrf as rf
import matplotlib.pyplot as plt
import pyvisa 

from Lakeshore335 import LakeShore335

# ---------------------------
# 仪器资源配置区
# ---------------------------
resource = 'GPIB0::20::INSTR'                 # VNA
laser_resource = 'TCPIP0::100.65.11.65::INSTR' # Keysight N7779C

RsInstrument.assert_minimum_version('1.53.0')
Instrument = RsInstrument(resource, True, False, "SelectVisa='ni'")
sleep(1)

def comprep():
    """Preparation of the communication"""
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
    print('Hello, I am VNA: ' + idnResponse)

def measure():
    """Perform a single sweep measurement"""
    Instrument.write_str_with_opc('INIT1:CONTinuous OFF')
    status = Instrument.write_str_with_opc('INIT1:IMMediate')
    return status

def saves2p(s2p_filename):
    """Save the measurement to a s2p file"""
    Instrument.write_str_with_opc(f'MMEMory:STORe:TRACe:PORTs 1, "{s2p_filename}", COMPlex, 1, 2')

def fileget(s2p_filename, pc_filename):
    """Transfer file from instrument to PC"""
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
            print("Hello, I am Laser:", self.inst.query('*IDN?').strip())
        except Exception as e:
            print(f"Failed to connect to Laser: {e}")
            raise e

    def set_power_mw(self, power_mw):
        """设置功率 (mW)"""
        self.inst.write(f':SOURce:POWer {power_mw}MW')
        
    def output_on(self):
        self.inst.write(':OUTPut:STATe ON')

    def output_off(self):
        self.inst.write(':OUTPut:STATe OFF')

    def close(self):
        self.inst.close()


# ---------------------------
# 主程序开始
# ---------------------------
comprep()
comcheck()

temp_reader = LakeShore335(visa_address="ASRL3::INSTR")
laser = KeysightLaser(laser_resource)

# ---------------------------
# 测试参数设置
# ---------------------------
power_initial = 5  # 初始功率 (mW)
power_target = 7   # 目标功率 (mW)
total_measurements = 20 # 连续测量次数

date = "20260521"
# 根据你的要求，保存在原路径 20260430 下（包含-25dBm层级），文件夹命名为 "5mW-7mW"
folder = rf'D:\YBCO\VNAMeas\data\{date}\-25dBm'
folder_data = os.path.join(folder, f'{power_initial}mW-{power_target}mW')

if not os.path.exists(folder_data):
    os.makedirs(folder_data)
    print(f"已创建数据文件夹: {folder_data}")

# 仪器内部暂存 s2p 的路径
s2p_filename_instrument = r'C:\2026\s2pfilename.s2p'

print("\n---------- 开始瞬态响应自动化测试 ----------")

# 1. 达到初始状态并等待
print(f">>> 步骤 1/3: 设置初始功率为 {power_initial} mW 并等待热稳定...")
laser.set_power_mw(power_initial)
laser.output_on()

# 等待 3 分钟 (180秒)
for remaining in range(180, 0, -10):
    print(f"稳定中，剩余等待时间: {remaining} 秒")
    sleep(10)

current_temp = temp_reader.get_temperature()
print(f"初始状态稳定完毕，当前温度: {current_temp} K")

# 2. 切换到目标功率
print(f"\n>>> 步骤 2/3: 瞬间切换功率至 {power_target} mW，即将开始连续扫描！")
laser.set_power_mw(power_target)

# 3. 连续无间隔测量
print(f">>> 步骤 3/3: 开始执行 {total_measurements} 次连续测量...")

# 用于记录每次测量完成的时间戳
time_records = []

for count in range(1, total_measurements + 1):
    
    # 获取实时温度 (如果读取温度较慢，且你只关心 S参数，可以将此行移到循环外，但这里保留以观测瞬态温度)
    current_temp = temp_reader.get_temperature()
    
    # 构造 PC 端文件名，按照记录顺序 1 到 20 命名
    pc_filename = os.path.join(folder_data, f'tlbco_transient_{count}_{current_temp:.3f}K.s2p')
    
    # 测量并存图
    measure()
    saves2p(s2p_filename_instrument)
    fileget(s2p_filename_instrument, pc_filename)
    
    # 记录当前时间戳
    current_time = time.time()
    time_records.append(current_time)
    
    print(f"  -> 第 {count}/{total_measurements} 次测量完成，已保存至: {os.path.basename(pc_filename)}")

# ---------------------------
# 后处理与清理
# ---------------------------
print("\n---------- 测量结束，设备安全关闭 ----------")
laser.output_off()
laser.close()
close()

# 计算平均测量间隔时间
if len(time_records) > 1:
    # 间隔数 = 测量次数 - 1
    total_duration = time_records[-1] - time_records[0]
    avg_interval = total_duration / (len(time_records) - 1)
    
    print(f"\n【耗时统计】")
    print(f"总计连续扫描次数: {total_measurements} 次")
    print(f"连续扫描总耗时: {total_duration:.2f} 秒")
    print(f"每次测量间的平均间隔时间: {avg_interval:.2f} 秒")
else:
    print("未获取到足够的测量时间数据。")

print('I am done')