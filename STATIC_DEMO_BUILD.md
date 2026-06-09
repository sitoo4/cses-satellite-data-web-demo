# Static Demo Build

`scripts/build_sanitized_static_demo.py` 用本地 H5 文件预生成 GitHub Pages 可读取的脱敏派生文件。脚本只读输入 H5，不复制原始 H5，不把 H5 写入 `frontend/public/`，也不输出完整逐点时间序列。

## 输出目录

```text
frontend/public/demo_data/
```

输出文件：

- `demo_manifest.json`
- `demo_summary.json`
- `demo_statistics.json`
- `demo_statistics_summary.csv`
- `magnetic_sanitized_downsampled.json`
- `orbit_points_sanitized.json`
- `magnetic_overview.png`
- `orbit_demo.html`

## 运行方式

在公开仓库中不要硬编码个人绝对路径。需要重新生成时，在本机用自己的 H5 路径传参：

```bash
python scripts/build_sanitized_static_demo.py \
  --input-file "/path/to/local/CSES_HPM_file_01.h5" \
  --input-file "/path/to/local/CSES_HPM_file_02.h5" \
  --input-file "/path/to/local/CSES_HPM_file_03.h5" \
  --input-file "/path/to/local/CSES_HPM_file_04.h5" \
  --input-file "/path/to/local/CSES_HPM_file_05.h5" \
  --input-file "/path/to/local/CSES_HPM_file_06.h5"
```

## 脱敏原则

- 原始 H5 不复制到仓库。
- JSON 只保存 demo 展示所需的摘要、统计、segment 范围和降采样展示点。
- `magnetic_sanitized_downsampled.json` 默认每 60 秒左右保留一个点，磁场值保留 1 位小数，并加入固定 seed 的极小确定性扰动。
- `orbit_points_sanitized.json` 默认每 120 秒左右保留一个点，经纬度保留 2 位小数，高度保留 1 位小数。
- 逐点质量 flag 序列不会输出，只输出 value counts 和 percent。
- `orbit_demo.html` 使用降采样轨道点，不包含原始路径和完整逐秒轨道。
- demo 文件中不记录本机 H5 路径、个人用户名路径或文件 hash。
- `demo_manifest.json` 只记录 `demo_segment_01` 这样的匿名 source label。

## 验证

```bash
find frontend/public/demo_data -maxdepth 1 -type f \( -name '*.h5' -o -name '*.hdf5' -o -name '*.cdf' -o -name '*.sav' \) -print
rg -n '(/Users/|/Volumes/)' frontend/public/demo_data || true
git ls-files | grep -Ei '\.(h5|hdf5|cdf|sav)$' || true
bash scripts/check_public_demo_safety.sh
```

期望结果：没有原始数据文件，没有本机路径，磁场和轨道 JSON 的点数是降采样后的数量。

## 前端构建

```bash
cd frontend
npm run test
npm run build
```

`npm run build` 默认使用 `VITE_DEMO_STATIC=true`。

## 限制

这个脚本生成的是 public demo 派生数据，不是正式科学产品。频谱图、STFT、wavelet、Pc5 PSD、电场图和太阳风图都不在静态 demo 范围内。
