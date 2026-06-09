# Sanitized Static Demo Report

## Summary

`public-demo` 已整理为“脱敏静态数据 demo”。GitHub Pages 版本不运行后端、不上传 H5、不读取浏览器本地 H5，只读取 `frontend/public/demo_data/` 下的脱敏派生文件。

## 本地输入源

本次本地生成使用了 6 个 CSES-01 HPM_5 H5 文件作为输入源。它们只在本机被 `scripts/build_sanitized_static_demo.py` 读取，没有复制进仓库，没有写入 `frontend/public/`，也没有在 JSON、CSV、前端页面或 README 中保留真实文件名。

公开 demo 中的 6 个文件显示名统一为：

- `demo_segment_01`
- `demo_segment_02`
- `demo_segment_03`
- `demo_segment_04`
- `demo_segment_05`
- `demo_segment_06`

## 生成的脱敏静态文件

输出目录：`frontend/public/demo_data/`

- `demo_manifest.json`
- `demo_summary.json`
- `magnetic_sanitized_downsampled.json`
- `orbit_points_sanitized.json`
- `demo_statistics.json`
- `demo_statistics_summary.csv`
- `magnetic_overview.png`
- `orbit_demo.html`

## 降采样和脱敏规则

磁场：

- 原始 `/B_FGM` 不完整输出。
- `magnetic_sanitized_downsampled.json` 默认约每 60 秒保留一个展示点。
- 输出字段为 `time_label`、`segment_id`、`source_id`、`Bx_demo`、`By_demo`、`Bz_demo`、`B_abs_demo`。
- 磁场值四舍五入到 1 位小数。
- 使用固定 random seed `20260609` 加入确定性小扰动，扰动标准差为对应分量标准差的 0.5%，并同时限制展示目的不受明显影响。
- 本次生成磁场 demo 点数：211。

轨道：

- GEO/MAG 位置不完整逐点输出。
- `orbit_points_sanitized.json` 默认约每 120 秒保留一个展示点。
- GEO_LAT/GEO_LON/MAG_LAT/MAG_LON 保留 2 位小数。
- ALTITUDE 保留 1 位小数。
- `orbit_demo.html` 使用降采样轨道点生成，不包含真实路径和完整逐秒轨道。
- 本次生成轨道 demo 点数：108。

时间：

- 不输出完整逐点 UTC_TIME 数组。
- demo summary 保留总起止时间和 segment 起止时间，精度到秒级。
- 降采样展示点使用 `T+HH:MM:SS` 相对时间标签和北京时间展示标签。

质量 flag：

- 不输出逐点 FLAG_MT、FLAG_SHW、FLAG_TBB、FLAG_N3 序列。
- 只输出 `value_counts` 和 `value_percent`。
- 前端中文解释：
  - FLAG_MT：磁力矩器干扰标志
  - FLAG_SHW：地影/日照状态
  - FLAG_TBB：TBB 开关状态
- `0` 不解释为“数据完全正常”，只解释为“该标志未触发”或“未标记”。

统计：

- `demo_statistics.json` 只包含聚合统计。
- 允许字段包括 count、min、max、mean、median、std、q25、q75、iqr 等。
- 统计数值经过合理四舍五入。
- 统计只用于 demo 展示，不代表正式科学产品。

## 安全确认

已加入 `scripts/check_public_demo_safety.sh`，检查内容包括：

- git 未跟踪 `.h5/.hdf5/.cdf/.sav`。
- `frontend/public/demo_data/` 不含 `.h5/.hdf5/.cdf/.sav`。
- demo 数据、前端源码和公开文档中不包含真实本机 HPM 路径、个人用户路径或真实 H5 文件名。
- JSON/CSV 文件大小在预期范围内，避免误输出完整逐点数据。
- `magnetic_sanitized_downsampled.json` 和 `orbit_points_sanitized.json` 点数为降采样后的数量。

## GitHub Pages 发布判断

可以安全作为 GitHub Pages 静态 demo 发布，前提是发布前继续通过：

```bash
python -m py_compile scripts/build_sanitized_static_demo.py
cd frontend && npm run test && npm run build
cd .. && bash scripts/check_public_demo_safety.sh
```


