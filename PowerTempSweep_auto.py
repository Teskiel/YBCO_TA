# -*- coding: utf-8 -*-

"""
Description:    Automated 2D Sweep (Temperature & Laser Power) for YBCO S-parameter measurement.
                Features:
                - LakeShore 335 sliding-window temperature stabilization.
                - STRICT heater range limitation (Max = Medium, High is forbidden).
                - Keysight N7779C step-sweep with 3-minute thermal relaxation.
"""

import os
import time
from time import sleep
from collections import deque
from RsInstrument import *
import pyvisa

# 假设你原本的 LakeShore335 驱动支持基本的读取和写入
from Lakeshore335 import LakeShore335

# ---------------------------
# 1. 仪器资源与基础配置
# ---------------------------
resource_vna = 'GPIB0::20::INSTR'
# resource_laser = 'TCPIP0::100.65.11.65::INSTR'
resource_laser = 'TCPIP0::100.65.11.65::inst0::INSTR'
resource_lakeshore = 'ASRL3::INSTR'

date = "20260509"
base_dir = rf'D:\YBCO\VNAMeas\data\{date}\-25dBm'

# 测试矩阵定义
temp_targets = [10, 20, 40, 77] # 温度目标 (K)
power_levels = [0, 1, 3, 5, 7, 9, 11, 13, 15, 17] # 激光功率 (mW)

# ---------------------------
# 2. VNA 控制模块 (保持原样)
# ---------------------------
RsInstrument.assert_minimum_version('1.53.0')
vna = RsInstrument(resource_vna, True, False, "SelectVisa='ni'")

def vna_setup():
    print(f'[VNA] VISA Manufacturer: {vna.visa_manufacturer}')
    vna.visa_timeout = 10000
    vna.opc_timeout = 40000
    vna.instrument_status_checking = True
    vna.clear_status()

def measure_and_save(s2p_instrument_path, pc_path):
    vna.write_str_with_opc('INIT1:CONTinuous OFF')
    vna.write_str_with_opc('INIT1:IMMediate')
    vna.write_str_with_opc(f'MMEMory:STORe:TRACe:PORTs 1, "{s2p_instrument_path}", COMPlex, 1, 2')
    vna.read_file_from_instrument_to_pc(s2p_instrument_path, pc_path)

# ---------------------------
# 3. Keysight 激光器模块
# ---------------------------
# class KeysightLaser:
#     def __init__(self, resource_name):
#         self.rm = pyvisa.ResourceManager()
#         self.inst = self.rm.open_resource(resource_name)
#         self.inst.timeout = 5000
#         print("[Laser] Connected to:", self.inst.query('*IDN?').strip())

#     def set_power_mw(self, power_mw):
#         self.inst.write(f':SOURce:POWer {power_mw}MW')
        
#     def output_on(self):
#         self.inst.write(':OUTPut:STATe ON')

#     def output_off(self):
#         self.inst.write(':OUTPut:STATe OFF')

#     def close(self):
#         self.inst.close()
class KeysightLaser:
    def __init__(self, resource_name):
        self.rm = pyvisa.ResourceManager()
        try:
            self.inst = self.rm.open_resource(resource_name)
            # 增加超时到 15 秒，应对可能的网络延迟
            self.inst.timeout = 15000 
            # 确认连接并清理之前可能残留的错误状态
            self.inst.write('*CLS')
            print("[Laser] Connected to:", self.inst.query('*IDN?').strip())
        except Exception as e:
            print(f"[Laser Error] 无法连接激光器: {e}")
            raise e

    def set_power_mw(self, power_mw):
        """设置激光器功率 (mW) 并确保操作完成"""
        self.inst.write(f':SOURce:POWer {power_mw}MW')
        # 强制等待仪器处理完当前指令
        self.inst.query('*OPC?') 
        time.sleep(0.5) 

    def output_on(self):
        self.inst.write(':OUTPut:STATe ON')
        self.inst.query('*OPC?')
        time.sleep(0.5)

    def output_off(self):
        self.inst.write(':OUTPut:STATe OFF')
        self.inst.query('*OPC?')

    def close(self):
        self.inst.close()
# ---------------------------
# 4. LakeShore 温度控制与稳定判断
# ---------------------------
class CryoController:
    def __init__(self, ls_inst):
        """传入你原有的 LakeShore335 实例对象"""
        self.ls = ls_inst
        # 为了发送 SCPI 指令，我们直接借用 pyvisa 的通信。如果你的 ls_inst 有专门的 write 方法，可替换。
        self.rm = pyvisa.ResourceManager()
        self.inst = self.rm.open_resource(resource_lakeshore) 
        
    def set_temperature_safe(self, target_k):
        """安全设置温度：限制加热档位"""
        # 设置目标温度 (假设 Loop 1 为主控)
        self.inst.write(f'SETP 1, {target_k}')
        
        # === 核心安全逻辑：禁止 High 档 ===
        # LakeShore 335 的 RANGE 指令: 0=Off, 1=Low, 2=Medium, 3=High
        # 4K, 10K 通常用 Low 足够；20K及以上可以用 Medium。禁止使用 3 (High)。
        if target_k <= 10:
            heater_range = 1 # Low
        else:
            heater_range = 2 # Medium
            
        self.inst.write(f'RANGE 1, {heater_range}')
        print(f"[Cryo] 设置目标温度: {target_k}K, 加热器已强制锁定在档位: {heater_range} (1=Low, 2=Med)")

    def get_temp(self):
        return self.ls.get_temperature()

    def wait_for_stability(self, target_k, tolerance=0.1, window_time=60, check_interval=5):
        """
        滑动窗口算法：观察过去 window_time (如60秒) 内的温度数据
        若最大值与最小值之差小于 tolerance，且平均值接近目标温度，则认为系统达到热力学稳态。
        """
        print(f"\n[Cryo] 等待温度稳定至 {target_k} K (容差 ±{tolerance}K, 窗口 {window_time}s)...")
        queue_size = window_time // check_interval
        temp_window = deque(maxlen=queue_size)
        
        while True:
            current_t = self.get_temp()
            temp_window.append(current_t)
            
            # 只有当队列填满了（已经观察了完整的时间窗口），才开始判断
            if len(temp_window) == queue_size:
                t_max = max(temp_window)
                t_min = min(temp_window)
                t_avg = sum(temp_window) / len(temp_window)
                
                fluctuation = t_max - t_min
                offset = abs(t_avg - target_k)
                
                print(f"  -> 实时监测: 当前={current_t:.3f}K, 波动幅度={fluctuation:.3f}K, 偏离度={offset:.3f}K", end='\r')
                
                # 如果波动很小，且整体在目标温度附近
                if fluctuation <= tolerance and offset <= (tolerance * 2):
                    print(f"\n[Cryo] 温度已稳定在 {t_avg:.3f} K！")
                    break
            else:
                print(f"  -> 收集背景数据中... ({len(temp_window)}/{queue_size}) 当前={current_t:.3f}K", end='\r')
                
            time.sleep(check_interval)

    def heater_off(self):
        """彻底关闭加热器"""
        self.inst.write('RANGE 1, 0')
        self.inst.write('SETP 1, 0')



# ---------------------------
# 修改后的主程序执行区
# ---------------------------
vna_setup()
laser = KeysightLaser(resource_laser)
base_ls335 = LakeShore335(visa_address=resource_lakeshore)
cryo = CryoController(base_ls335)

instrument_s2p = r'C:\2026\s2pfilename.s2p'
meas_count = 1

try:
    print("\n================ 开始二维参数矩阵测试 ================")
    
    # 外层循环：遍历温度
    for target_T in temp_targets:
        print(f"\n=======================================================")
        print(f"  正在处理目标温区: {target_T} K")
        print(f"=======================================================")
        
        # --- 新增逻辑：4K-5K 特殊温区预检 ---
        current_t_start = cryo.get_temp()
        
        # 判断条件：当前循环目标是 4K，且系统实测已经在 4K-5K 之间
        if target_T == 4 and 4.0 < current_t_start < 5.0:
            print(f"[Mode] 检测到起始温度为 {current_t_start:.3f}K (4K-5K区间)，跳过加热设置，直接进行稳态判定。")
            # 以当前实测温度作为稳定性判定的基准值
            target_T_ref = current_t_start  
            # 文件夹和文件命名的标签改为实时温度
            folder_T_label = f"{current_t_start:.3f}K"
        else:
            # 正常逻辑：设置目标温度并安全限制功率
            cryo.set_temperature_safe(target_T)
            target_T_ref = target_T
            folder_T_label = f"{target_T}K"
        # -----------------------------------
        
        # 稳定性判定（使用动态确定的 target_T_ref）
        cryo.wait_for_stability(target_T_ref, tolerance=0.1, window_time=60, check_interval=5)
        
        # 创建第一级文件夹：使用 folder_T_label (可能是 "4K" 或 "4.214K")
        temp_dir = os.path.join(base_dir, f'Temp_{folder_T_label}')
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)
            
        # 内层循环：遍历激光功率
        for target_P in power_levels:
            print(f"\n>>> 开始 {folder_T_label} 下的 {target_P}mW 测量环境准备...")
            
            if target_P == 0:
                laser.output_off()
            else:
                laser.set_power_mw(target_P)
                laser.output_on()
                
            # 切换功率后的固定热稳定等待时间 (1分钟)
            print("等待 1 分钟让激光热效应系统稳定...")
            for remaining in range(60, 0, -10):
                print(f"  剩余等待时间: {remaining} 秒", end='\r')
                sleep(10)
            
            # 读取实际测量瞬间的温度
            real_t = cryo.get_temp()
            
            # 创建第二级文件夹：同步使用实时温度标签
            power_dir = os.path.join(temp_dir, f'{folder_T_label}-{target_P}mW-laser')
            if not os.path.exists(power_dir):
                os.makedirs(power_dir)
                
            # 构造文件名
            filename = f'tlbco_T{folder_T_label}_P{target_P}mW_meas_{meas_count:03d}_{real_t:.3f}K.s2p'
            pc_s2p_path = os.path.join(power_dir, filename)
            
            # 执行测量并保存
            print(f"执行 VNA 扫描，保存路径：{filename}")
            measure_and_save(instrument_s2p, pc_s2p_path)
            
            meas_count += 1

except KeyboardInterrupt:
    print("\n\n[Warning] 检测到人工手动中断 (Ctrl+C)！正在执行安全清理程序...")

except Exception as e:
    print(f"\n\n[Error] 程序运行中发生错误: {e}\n正在执行安全清理程序...")

finally:
    # ---------------------------
    # 安全收尾机制 (致命重要)
    # ---------------------------
    print("\n================ 执行系统安全收尾 ================")
    try:
        laser.output_off()
        laser.close()
        print("[Safe] 激光器已关闭并断开连接。")
    except:
        pass
        
    try:
        cryo.heater_off()
        print("[Safe] LakeShore 加热器已设置为 0K 并切断输出。")
    except:
        pass
        
    try:
        vna.close()
        print("[Safe] VNA 连接已断开。")
    except:
        pass
        
    print("================ 自动化流程完全结束 ================")