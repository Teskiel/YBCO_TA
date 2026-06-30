# Design Spec: 五谐振器对比表征简报 PPT

**Date**: 2026-06-18
**Status**: approved
**Scope**: 单次生成，替换 v7 单谐振器 PPT

## 目标

基于全部 5 个 YBCO KID 谐振器的分析数据，生成一份主题对比式简报 PPT。

## 五个谐振器

| 编号 | 频率 | 6K dip |
|------|------|--------|
| R1 | 3.84602 GHz | -5.80 dB |
| R2 | 4.00958 GHz | -4.33 dB |
| R3 | 4.50021 GHz | -5.98 dB |
| R4 | 4.99696 GHz | -17.74 dB |
| R5 | 5.25161 GHz | -6.10 dB |

## 数据组织

```
output/merged/
├── 01_resonance_detection/     ← 共用：频谱总览 + 寻峰标注
├── 04_S21_temperature_overlay/ ← 共用
├── R1_3.846GHz/                ← pixel_indx=0
│   ├── 02_f0_temperature/
│   ├── 03_Qi_temperature/
│   ├── 05_optical_response_6K/
│   ├── 06_optical_response_highT/
│   ├── 07_responsivity_temperature/
│   └── 08_per_temp_raw/
├── R2_4.010GHz/                ← pixel_indx=1
├── R3_4.500GHz/                ← pixel_indx=2
├── R4_4.997GHz/                ← pixel_indx=3
└── R5_5.252GHz/                ← pixel_indx=4
```

## PPT 结构 (~18 页)

1. 封面
2. 频谱总览（寻峰图 + 五谐振器标注）
3. f₀(T) 五线对比
4. Qi(T) 五线对比
5-8. 6K/20K/40K/77K 光响应对比（每页五谐振器 res shift 并排）
9. 响应率 vs T 五线对比
10-14. 各谐振器独立概览（1 页/谐振器：f₀+Qi+S21 overlay）
15-17. R4 详情（最深 dip 谐振器：6K/40K/77K 三温度 S21）
18. 小结

## 实现

- 新脚本 `generate_all_resonators.py`：循环 pixel_indx 0→4，调用分析流程，输出到对应子文件夹
- 新脚本 `generate_ppt_v8.py`：从重组后的 merged/ 读取，生成主题对比式 PPT
