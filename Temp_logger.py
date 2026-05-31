# -*- coding: utf-8 -*-
"""
Created on Sat Jan  3 11:00:44 2026

@author: DELL
"""

import time
from datetime import datetime

from Lakeshore335 import LakeShore335

def log_temperature(temp_reader, logfile="temperature_log.txt", interval=1.0):
    """
    持续记录温度
    :param temp_reader: 具有 get_temperature() 方法的对象
    :param logfile: 日志文件名
    :param interval: 采样间隔（秒）
    """
    # 写表头（若文件不存在）
    try:
        with open(logfile, "x") as f:
            f.write("timestamp,temperature\n")
    except FileExistsError:
        pass

    while True:
        current_temp = temp_reader.get_temperature()
        timestamp = datetime.now().isoformat()

        with open(logfile, "a") as f:
            f.write(f"{timestamp} {current_temp}\n")

        time.sleep(interval)

temp_reader  = LakeShore335(visa_address= "ASRL3::INSTR")

log_temperature(temp_reader, interval=2.0)


