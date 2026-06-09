# CSES HPM Static Web Demo

CSES-01 HPM 卫星数据可视化演示，包含磁场、轨道和统计数据视图，所使用数据已基于原始数据生成脱敏派生 demo。

张衡一号 CSES-01 HPM 数据分析网页的公开展示版。这个分支面向 GitHub Pages、简历和作品集，只展示预生成的脱敏派生数据，不包含原始 H5 文件，不包含全分辨率逐点时间序列，也不依赖任何个人本机数据目录。

## What It Shows

- 张衡一号 HPM demo 数据范围和北京时间显示。
- 预生成磁场总览图：Bx、By、Bz、`|B|`。
- 预生成交互式轨道图：可鼠标拖动，包含经纬度网格和 segment 标注。
- 描述性统计摘要：时间范围、样本数、segment 数、采样间隔、`B_abs`、GEO 位置范围、质量标志分布。
- demo 统计结果下载：`demo_statistics_summary.csv`、`demo_statistics.json`、`demo_manifest.json`。
- 降采样展示数据：`magnetic_sanitized_downsampled.json` 和 `orbit_points_sanitized.json`。

## What It Does Not Do

- 不上传 H5。
- 不在浏览器读取 H5。
- 不运行 FastAPI 后端。
- 不提供原始 H5 下载。
- 不提供完整逐点 UTC_TIME、B_FGM 或逐点质量标志序列。
- 不调用 `/api`。
- 不生成频谱图、STFT、wavelet、Pc5 PSD 或正式科学结论。

频谱图按钮保留为 disabled，提示原因是：`涉及其他数据，demo 版本不支持展示`。

## Repository Layout

```text
frontend/
  public/demo_data/        # GitHub Pages 读取的脱敏派生 demo 文件
  public/mascots/          # 静态页面素材
  src/                     # React/Vite 前端
scripts/
  build_sanitized_static_demo.py
  check_public_demo_safety.sh
backend/
  app/                     # 本地完整版后端代码，GitHub Pages 不运行
```

`frontend/public/demo_data/` 当前包含：

- `demo_manifest.json`
- `demo_summary.json`
- `demo_statistics.json`
- `demo_statistics_summary.csv`
- `magnetic_sanitized_downsampled.json`
- `orbit_points_sanitized.json`
- `magnetic_overview.png`
- `orbit_demo.html`

这些都是脱敏派生结果，不是原始 H5，也不是完整逐点数据重建。

## Quick Start: GitHub Pages Static Demo

```bash
cd frontend
npm install
npm run build
```

`npm run build` 默认设置 `VITE_DEMO_STATIC=true`，生成可静态托管的 `frontend/dist/`。

本地预览：

```bash
cd frontend
npm run dev
```

`npm run dev` 默认也是静态 demo 模式，不会请求后端 API。

如果部署在仓库子路径，可以设置 Vite base：

```bash
cd frontend
VITE_BASE_PATH=/your-repo-name/ npm run build
```

## Static Demo Behavior

当 `VITE_DEMO_STATIC=true` 时：

- 前端只读取相对路径 `/demo_data/...` 下的脱敏 JSON、CSV、PNG、HTML。
- 上传按钮只保留视觉位置，点击后提示：`当前为 demo，脱敏数据已准备，不支持上传`。
- 运行记录显示：`当前为 demo，不提供运行日志服务`。
- 裁剪区作为 demo 信息展示，不实时裁剪 H5。
- 导出按钮只下载预生成的 demo 统计结果，不导出原始数据或完整逐点数据。

## Local Full Version

本仓库仍保留本地完整版后端代码，适合在私有环境中上传用户自己的 H5 文件并实时解析、排序、去重、分段、绘图、统计和导出。GitHub Pages 不会运行这些能力。

本地完整版示例：

```bash
PYTHONPATH=backend python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
cd frontend
npm run dev:local
```

用户需要自己准备本地 H5 文件。不要把原始 H5 放进仓库。

## Regenerating Demo Data

`scripts/build_sanitized_static_demo.py` 只在本地运行，用本机允许访问的 H5 文件生成脱敏派生文件到 `frontend/public/demo_data/`。脚本不会复制原始 H5，也不会输出完整 1 Hz 时间序列。

详见 [STATIC_DEMO_BUILD.md](STATIC_DEMO_BUILD.md)。

## Smoke Test

```bash
python -m py_compile scripts/build_sanitized_static_demo.py
cd frontend
npm run test
npm run build
cd ..
bash scripts/check_public_demo_safety.sh
```

安全检查：

```bash
git ls-files | grep -Ei '\.(h5|hdf5|cdf|sav)$' || true
find frontend/public/demo_data -maxdepth 1 -type f \( -name '*.h5' -o -name '*.hdf5' -o -name '*.cdf' -o -name '*.sav' \) -print
rg -n '(/Users/|/Volumes/)' frontend/public/demo_data || true
```

## Known Limits

- demo 数据是脱敏降采样派生样例，只用于展示网页交互和工程数据流。
- 时间语义、变量含义和质量标志解释仍需要产品文档确认后才能用于正式科学分析。
- 静态版本不支持任意文件上传、任意时间裁剪、实时导出、后端运行日志或全分辨率数据下载。
- 频谱图、电场图和太阳风图不属于当前 public demo。
