# -*- coding: utf-8 -*-
"""
Description: YBCO 激光功率自动扫描程序 (温点智能识别 + 实时温度双注入版)
Setup: 温度手动控制，程序自动识别当前最接近的理论温点(4/10/20/40/77 K)，
       并将此时此刻的真实温度写入文件夹名与文件名中。
Date: 20260529
"""

import os
import time
from time import sleep
import pyvisa
import sys
from Lakeshore335 import LakeShore335

# ---------------------------
# 1. 仪器资源配置区
# ---------------------------
# 新 Keysight VNA HiSLIP 本地资源地址
resource_vna = 'TCPIP0::DESKTOP-1PLPGMT::hislip_PXI10_CHASSIS2_SLOT1_INDEX0::INSTR'
# 激光器 IP 地址
laser_resource = 'TCPIP0::100.65.11.65::INSTR' 
# 温度计串口地址
resource_lakeshore = 'ASRL4::INSTR'

# 🎯 Keysight VNA 软件界面左上角显示的 Trace 名字，请确保完全一致
TRACE_NAME = "CH1_S21_1"

# 基础文件目录
date = "20260529"
base_folder = rf'D:\YBCO\VNAMeas\data\{date}\-45dBm'
os.makedirs(base_folder, exist_ok=True)

# 扫描的功率列表 (单位: mW)
power_levels = [0, 1, 3, 5, 7, 9, 11, 13, 15, 17]

# power_levels = [7,9, 11, 13]

# ---------------------------
# 2. 激光器控制模块
# ---------------------------
class KeysightLaser:
    def __init__(self, resource_name):
        rm = pyvisa.ResourceManager()
        try:
            self.inst = rm.open_resource(resource_name)
            self.inst.timeout = 5000
            print("[OK] 激光器连接成功:", self.inst.query('*IDN?').strip())
        except Exception as e:
            print(f"[Error] 激光器连接失败: {e}")
            raise e

    def set_power_mw(self, power_mw):
        """设置激光器功率 (mW)"""
        self.inst.write(f':SOURce:POWer {power_mw}MW')
        
    def output_on(self):
        self.inst.write(':OUTPut:STATe ON')

    def output_off(self):
        self.inst.write(':OUTPut:STATe OFF')

    def close(self):
        self.inst.close()

# ---------------------------
# 3. 硬件初始化与握手
# ---------------------------
print("="*40)
print("开始硬件连接自检")
print("="*40)

rm = pyvisa.ResourceManager('visa32.dll')

# 初始化新 VNA
try:
    vna = rm.open_resource(resource_vna)
    vna.timeout = 120000  # 给扫描留足超时时间
    print(f"[OK] Keysight VNA 连接成功: {vna.query('*IDN?').strip()}")
except Exception as e:
    print(f"[Error] VNA 连接失败，请检查通道是否被占用: {e}")
    sys.exit(0)

# 初始化激光器
laser = KeysightLaser(laser_resource)

# 初始化温度计并注入底层“7位数据位+奇校验”暗号，防止超时
temp_reader = LakeShore335(visa_address=resource_lakeshore)
if "ASRL" in resource_lakeshore.upper():
    for attr in ['inst', 'visa', 'device', 'ser', 'com']:
        if hasattr(temp_reader, attr):
            target = getattr(temp_reader, attr)
            if hasattr(target, 'baud_rate'):
                target.baud_rate = 57600
                target.data_bits = 7
                target.parity = pyvisa.constants.Parity.odd
                target.read_termination = '\n'
                target.write_termination = '\n'

try:
    print(f"[OK] LakeShore335 当前初始温度读数: {temp_reader.get_temperature()} K")
except Exception as e:
    print(f"[Warning] 温度计读取初始失败（不影响后续尝试）: {e}")

# ---------------------------
# 4. 自动化功率扫描主循环
# ---------------------------
count = 0
print("\n" + "-"*10 + " 开始自动化功率测试流程 " + "-"*10)

try:
    for power in power_levels:
        print(f"\n>>> 正在准备 {power} mW 的测量环境...")
        if power == 0:
            laser.output_off()
            print("激光器输出已关闭 (0 mW)。")
        else:
            laser.set_power_mw(power)
            laser.output_on()
            print(f"激光器已设置为 {power} mW 且输出已开启。")

        # 等待 3 分钟让温度/状态稳定
        print("等待 3 分钟让系统状态稳定...")
        for remaining in range(10, 0, -10):
            print(f"剩余等待时间: {remaining} 秒", end='\r')
            sleep(10)
        print("\n稳定时间到，正在抓取此时此刻的温度...")
            
        # 🎯 【核心修改 1】：读取此时此刻的真实温度
        try:
            current_temp = temp_reader.get_temperature()
        except Exception as e:
            print(f"[Error] 采集时温度读取失败: {e}，将使用安全兜底值 4.0K")
            current_temp = 4.0

        # 🎯 【核心修改 2】：算法自动寻找最接近的理论目标温度点 (4, 10, 20, 40, 77)
        theoretical_targets = [4,5,10,20,30,40,50,60,70,77]
        closest_target = min(theoretical_targets, key=lambda x: abs(x - current_temp))
        
        print(f"【实时状态】实际温度: {current_temp:.3f} K | 自动归类至理论温点: {closest_target}K")

        # # 🎯 【核心修改 3】：在一级子文件夹名中同时加入【理论温点】和【此时此刻真实温度】
        # # 示例名：4K-5mW-laser_4.123K
        # folder_name = f'{closest_target}K-{power}mW-laser_{current_temp:.3f}K'
        # folder_data = os.path.join(base_folder, folder_name)
        # os.makedirs(folder_data, exist_ok=True)

        # # 🎯 【核心修改 4】：在文件名中同样注入此时此刻的实时温度
        # filename = f'tlbco_in_cryostat201_small_3_6GHz_light_{count}_{current_temp:.3f}K.s2p'
        # pc_filename = os.path.join(folder_data, filename)
        
        # =================================================================
        # 🎯 新增修改 1：将功率数字格式化为两位数 (例如 0->00, 3->03, 11->11)
        # =================================================================
        power_str = f"{power:02d}"

        # =================================================================
        # 🎯 新增修改 2：拆开原来的单层文件夹，用 os.path.join 建立两层嵌套目录
        # 第一层：base_folder \ 77K
        # 第二层：00mW-laser_77.037K
        # =================================================================
        folder_data = os.path.join(base_folder, f"{closest_target}K", f"{power_str}mW-laser_{current_temp:.3f}K")
        os.makedirs(folder_data, exist_ok=True)

        # =================================================================
        # 🎯 新增修改 3：规范化 s2p 文件的存盘名称格式，写为 YBCO_00mW_77.037K.s2p
        # =================================================================
        filename = f'YBCO_{power_str}mW_{current_temp:.3f}K.s2p'
        pc_filename = os.path.join(folder_data, filename)
        
        # 执行 Keysight VNA 单次触发扫描
        # print("VNA 开始单次扫描...")
        # vna.write(':INIT:CONT OFF')  # 关闭连续扫描
        # vna.write(':INIT:IMM')       # 触发单次扫描
        # vna.query('*OPC?')           # 阻塞等待扫描彻底结束

        # # 将 Trace 数据保存至本地
        # print(f"正在将数据保存至: {pc_filename}")
        # # vna.write(f':MMEM:STOR:TRAC "{TRACE_NAME}", "{pc_filename}"')
        # # 🎯 更换为 Keysight 矢网标准 2-Port S2P 导出指令
        # vna.write(f'CALCulate1:DATA:SNP:PORTs:SAVE "1,2", "{pc_filename}"')
        # count += 1
        
        # 执行 Keysight VNA 单次触发扫描
        # print("VNA 开始单次扫描...")
        # vna.write(':INIT:CONT OFF')  # 关闭连续扫描
        # vna.write(':INIT:IMM')       # 触发单次扫描
        # vna.query('*OPC?')           # 阻塞等待扫描彻底结束

        # # =================================================================
        # # 🎯 核心修复 1：将路径中的所有反斜杠 \ 替换为正斜杠 /
        # # 彻底消除 Keysight 内部解析器将 "\tlbco" 误判为 "Tab制表符" 的物理硬伤！
        # # =================================================================
        # vna_safe_path = pc_filename.replace('\\', '/')
        # print(f"正在将数据保存至: {vna_safe_path}")

        # # =================================================================
        # # 🎯 核心修复 2：使用 Keysight PNA 架构最标准的 2-Port S2P 存储指令
        # # 参数顺序： "文件全路径", "文件格式(S2P)", "数据源(Data)", 端口1, 端口2
        # # =================================================================
        # vna.write(f'MMEMory:STORe:DATA "{vna_safe_path}", "S2P", "Data", 1, 2')
        
        # count += 1
        
        # 执行 Keysight VNA 单次触发扫描
        print("VNA 开始单次扫描...")
        vna.write(':INIT:CONT OFF')  # 关闭连续扫描
        vna.write(':INIT:IMM')       # 触发单次扫描
        vna.query('*OPC?')           # 阻塞等待扫描彻底结束

        # =================================================================
        # 🎯 路径安全转换（保留，防止斜杠引发 \t 变制表符的惨剧）
        # =================================================================
        vna_safe_path = pc_filename.replace('\\', '/')
        print(f"正在指令发送，目标路径: {vna_safe_path}")

        # =================================================================
        # 🎯 方案一（最推荐）：标准 PNA 自动识别导出
        # 矢网底层会直接根据你文件名的 ".s2p" 后缀，自动剥离并导出 1,2 端口数据
        # =================================================================
        vna.write(f'MMEMory:STORe "{vna_safe_path}"')

        # =================================================================
        # 🎯 方案二（备用）：如果方案一没动静，解开这行的注释。
        # 这是显式指定端口的命令，但必须配合我们已经洗干净的 vna_safe_path
        # =================================================================
        # vna.write(f'CALCulate1:DATA:SNP:PORTs:SAVE "1,2", "{vna_safe_path}"')
        
        # =================================================================
        # 🔍 调试大杀器：主动抓取矢网内部的报错
        # 如果文件还没出来，控制台会清晰打印出矢网拒绝你的真正原因（比如路径非法或权限问题）
        # =================================================================
        vna_msg = vna.query(':SYSTem:ERRor?').strip()
        print(f"【矢网硬件反馈】: {vna_msg}")
        
        count += 1
        
except Exception as main_err:
    print(f"\n[System Error] 运行中遭遇异常: {main_err}")

finally:
    # ---------------------------
    # 5. 安全退出及资源释放
    # ---------------------------
    print("\n" + "="*40)
    print("正在安全关闭设备...")
    print("="*40)
    try:
        laser.output_off()
        laser.close()
        vna.close()
    except Exception as e:
        print(f"关闭资源时出现小插曲: {e}")
    print('测试脚本安全退出。')