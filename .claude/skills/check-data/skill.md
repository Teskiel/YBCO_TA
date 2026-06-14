---
name: check-data
description: 分析合并后实验数据完整性，生成缺失报告和补测清单
---

# 检查实验数据完整性

## 用法

```
/check-data <数据目录>
```

默认参数：温度 6-80K step 2，VNA -25/-30/-45 dBm，激光 0/1/3/5/7/9 mW。

可选：`--format json --output report.json` 导出补测清单。

## 执行

调用 `Data_process/completeness_checker.py`，table 格式直接展示，json 格式保存文件。
