# -*- coding: utf-8 -*-
"""
Created on Mon May 26 15:12:48 2025

@author: Hu Jie
"""

import pyvisa
import time
import csv
from datetime import datetime

# === 参数设置 ===
gpib_address = 'GPIB0::20::INSTR'
output_file = 'zva_marker1_log.csv'
interval_seconds = 0.5  # 每隔多少秒读取一次

# === 初始化 VISA 连接 ===
rm = pyvisa.ResourceManager()
inst = rm.open_resource(gpib_address)

# === 确保 Marker1 被激活 ===
inst.write(':CALC1:PAR1:SEL')
inst.write(':CALC1:MARK1:STAT ON')

# === 打开 CSV 文件并写入表头 ===
with open(output_file, mode='w', newline='') as file:
    writer = csv.writer(file)
    writer.writerow(['Timestamp', 'Marker1_X', 'Marker1_Y'])

    try:
        while True:
            # 当前时间
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # 读取 Marker1 的 X 和 Y 值
            x_val = float(inst.query(':CALC1:MARK1:X?'))
            y_val = float(inst.query(':CALC1:MARK1:Y?'))

            # 写入文件
            writer.writerow([timestamp, x_val, y_val])
            print(f"{timestamp} | X = {x_val:.4f} | Y = {y_val:.4f}")

            # 延时
            time.sleep(interval_seconds)

    except KeyboardInterrupt:
        print("\n已停止采集，数据已保存至文件。")

# === 关闭连接 ===
inst.close()
