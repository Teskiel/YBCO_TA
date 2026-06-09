# -*- coding: utf-8 -*-
"""
Description: YBCO S-parameter 2D Sweep (Temp & Laser) - Keysight & LakeShore 335 完美适配版
Date: 20260527
Features: 
- 成功握手 Keysight P5003A VNA (HiSLIP)
- 修正 LakeShore 335 结束符为 '\n'，波特率对齐 NI MAX 截图的 9600
- 消除串口多重打开的资源锁死隐患
"""

import os
import time
import pyvisa
import numpy as np
import sys  
from collections import deque
from Lakeshore335 import LakeShore335

# ==========================================
# 1. 配置参数
# ==========================================
resource_vna = 'TCPIP0::127.0.0.1::hislip_PXI10_CHASSIS1_SLOT1_INDEX0::INSTR'
resource_laser = 'TCPIP0::100.65.11.65::INSTR'
resource_lakeshore = 'ASRL4::INSTR'  # 确认对应电脑的 COM4 接口

# 💡 核心串口参数对齐（依据 NI MAX 截图 9600 设定，若连不上可在面板修改此处为 57600）
LS_BAUD_RATE = 57600 

date_str = "20260609"
base_dir = rf'D:\YBCO\VNAMeas\data\{date_str}\-45dBm'
os.makedirs(base_dir, exist_ok=True)

# 🎯 Keysight VNA 窗口当前的 Trace 名字，必须与软件界面左上角完全一致
TRACE_NAME = "CH1_S21_1"

# temp_targets = [4, 10, 20, 40, 77]
temp_targets = [77]
power_levels = [0, 1, 3, 5, 7, 9, 11, 13, 15, 17]

# ==========================================
# 2. 硬件自检函数
# ==========================================
def hardware_self_check():
    print("\n" + "="*40)
    print("阶段一：硬件通讯自检")
    print("="*40)
    rm = pyvisa.ResourceManager('visa32.dll')
    
    # 1. 试探 VNA
    try:
        vna_test = rm.open_resource(resource_vna)
        print(f"[OK] VNA 响应: {vna_test.query('*IDN?').strip()}")
        vna_test.close()
    except Exception as e:
        print(f"[Check Failed] VNA 通讯失败 @ {resource_vna}\n错误详情: {e}")
        return False
        
    # 2. 试探 LakeShore 温度计
    try:
        # 🎯 核心修复：结束符严格使用 '\n'，波特率对齐 9600
        ls_test = rm.open_resource(resource_lakeshore, read_termination='\n', write_termination='\n')
        ls_test.baud_rate = LS_BAUD_RATE
        print(f"[OK] LakeShore 响应: {ls_test.query('*IDN?').strip()}")
        ls_test.close()
    except Exception as e:
        print(f"[Check Failed] LakeShore 温度计通讯失败 @ {resource_lakeshore}")
        print(f"错误详情: {e}")
        print("💡 提示：若依然超时，请检查 LakeShore 前面板 [Interface] 按钮里的 Baud rate 是否为 9600？")
        return False
    
    # 3. 试探 激光器
    try:
        laser_test = rm.open_resource(resource_laser)
        print(f"[OK] 激光器响应: {laser_test.query('*IDN?').strip()}")
        laser_test.close()
    except Exception as e:
        print(f"[Check Failed] 激光器通讯失败 @ {resource_laser}\n错误详情: {e}")
        return False
        
    print("[OK] 所有硬件链路物理握手成功！")
    return True

# ==========================================
# 3. 核心控制类
# ==========================================
class AdvancedCryoController:
    def __init__(self, ls_obj, visa_addr):
        # 🎯 架构优化：直接复用外部传入的 ls_obj，不要在内部重新 open_resource 造成串口冲突
        self.ls = ls_obj
        self.rm = pyvisa.ResourceManager('visa32.dll')
        # 内部控制句柄同样遵循 '\n' 与匹配的波特率
        self.inst = self.rm.open_resource(visa_addr, read_termination='\n', write_termination='\n')
        self.inst.baud_rate = LS_BAUD_RATE

    def set_temp_safe(self, target_k):
        """设置温度并根据温区自动切换 Range"""
        if target_k <= 5:
            print(f"[Cryo] 低温目标 {target_k}K：关闭加热器执行底温测试。")
            self.inst.write('RANGE 1, 0')
        else:
            h_range = 1 if target_k < 15 else 2 # 15K以下Low, 以上Medium
            self.inst.write(f'SETP 1, {target_k}')
            self.inst.write(f'RANGE 1, {h_range}')
            print(f"[Cryo] 设置目标: {target_k}K, 加热档位: {h_range}")

    def smart_wait_for_stability(self, target_k):
        """双重指标稳态判定"""
        print(f"\n[Cryo] 正在监测稳态 (目标 {target_k}K)...")
        
        # 第一阶段：快速接近门槛
        while True:
            curr_t = self.ls.get_temperature()
            if abs(curr_t - target_k) <= 0.5:
                print(f"\n[Cryo] 进入临界区，启动 5 分钟滑动窗口分析...")
                break
            print(f"  [接近中] 当前: {curr_t:.3f}K | 差距: {abs(curr_t-target_k):.3f}K", end='\r')
            time.sleep(10)

        # 第二阶段：滑动窗口判定
        window_size = 60 # 5秒一次，共5分钟
        temp_queue = deque(maxlen=window_size)
        
        while True:
            curr_t = self.ls.get_temperature()
            temp_queue.append(curr_t)
            
            if len(temp_queue) == window_size:
                avg_t = sum(temp_queue) / window_size
                offset = abs(avg_t - target_k)
                drift = max(temp_queue) - min(temp_queue)
                
                print(f" [判定中] 偏差: {offset:.3f}K | 波动: {drift:.3f}K    ", end='\r')
                
                if offset <= 0.2 and drift <= 0.1:
                    print(f"\n[Cryo] 稳态达成！最终均值: {avg_t:.3f}K")
                    return avg_t
            else:
                print(f" [采样中] 进度: {len(temp_queue)}/{window_size} | 当前: {curr_t:.3f}K    ", end='\r')
            
            time.sleep(5)

class KeysightLaser:
    def __init__(self, resource_name):
        rm = pyvisa.ResourceManager('visa32.dll')
        self.inst = rm.open_resource(resource_name)
        self.inst.timeout = 15000

    def set_power(self, mw):
        if mw <= 0:
            self.inst.write(':OUTPut:STATe OFF')
            print(f"-> 激光器已关闭")
        else:
            self.inst.write(f':SOURce:POWer {mw}MW')
            self.inst.write(':OUTPut:STATe ON')
            print(f"-> 激光器功率已切换至: {mw} mW")
        time.sleep(0.5)

# ==========================================
# 4. 主程序
# ==========================================
if __name__ == "__main__":
    if not hardware_self_check():
        print("[System Exit] 硬件自检未通过，程序安全退出。")
        sys.exit(0)

    # 1. 初始化底层 VISA 资源接管 Keysight VNA
    rm_vna = pyvisa.ResourceManager('visa32.dll')
    vna = rm_vna.open_resource(resource_vna)
    vna.timeout = 120000 
    
    # 2. 初始化激光器与温控核心
    laser = KeysightLaser(resource_laser)
    base_ls335 = LakeShore335(visa_address=resource_lakeshore)
    cryo = AdvancedCryoController(base_ls335, resource_lakeshore)

    meas_count = 1
    
    try:
        for t_goal in temp_targets:
            print(f"\n" + "="*50 + f"\n开始处理目标温度: {t_goal} K\n" + "="*50)
            
            cryo.set_temp_safe(t_goal)
            final_stable_t = cryo.smart_wait_for_stability(t_goal)
            
            t_label = f"{t_goal}K" if t_goal > 5 else f"{final_stable_t:.3f}K"
            temp_path = os.path.join(base_dir, f"Temp_{t_label}")
            os.makedirs(temp_path, exist_ok=True)

            for p_mw in power_levels:
                print(f"\n>>> 功率切换: {p_mw} mW")
                laser.set_power(p_mw)
                
                print("[Cryo] 监测激光引入的热扰动...")
                real_time_t = cryo.smart_wait_for_stability(t_goal)
                
                filename = f"ybco_T{t_label}_P{p_mw}mW_#{meas_count:03d}_{real_time_t:.3f}K.s2p"
                pc_save_path = os.path.join(temp_path, filename)
                
                print(f"[VNA] 正在执行单次扫描及数据本地下传: {filename}")
                vna.write(':INIT:CONT OFF')
                vna.write(':INIT:IMM')
                vna.query('*OPC?')  # 同步阻塞直到扫描结束
                
                # 将 Trace 数据安全存入本地
                vna.write(f':MMEM:STOR:TRAC "{TRACE_NAME}", "{pc_save_path}"')
                
                meas_count += 1

    except Exception as e:
        print(f"\n[System Error] 错误详情: {e}")
    finally:
        print("\n正在安全停机...")
        try:
            laser.set_power(0)
            cryo.inst.write('RANGE 1, 0')
            vna.close()
            cryo.inst.close()
        except: pass
        print("实验安全结束。")