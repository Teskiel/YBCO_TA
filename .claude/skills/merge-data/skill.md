---
name: merge-data
description: 合并多次拆分运行的实验数据碎片，去重后输出统一扁平目录
---

# 合并实验数据碎片

## 用法

```
/merge-data <碎片目录...>
```

可选：`--output <dir>` 指定输出目录（默认 `experiment_data/merged`），`--dry-run` 仅预览。

## 执行

调用 `Data_process/experiment_merger.py`，始终先建议 `--dry-run`，用户确认后再真实合并。

完成后提示运行 `/check-data`。
