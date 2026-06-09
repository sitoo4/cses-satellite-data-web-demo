# 卫星数据分析仪表台网页说明文档

更新日期：2026-06-07

本文档说明 `<repo>` 当前网页的实际使用方式和功能边界。它描述的是当前前端页面，不是正式科学产品说明，也不是 CSES 数据处理上线文档。

## 1. 当前定位

这个网页是一个本地卫星数据工作台，用于在浏览器中查看和验证已有处理产品。

当前支持两个数据源入口：

- `Cluster 频谱保留`：读取 `<cluster_processed_root>` 中已经存在的 Cluster C1 处理产品，并在 Web 项目自己的 `outputs/generated_plots/cluster/` 下再生成图件。
- `CSES 磁场实验`：读取本机 CSES-01 HPM H5 文件索引和检查结果，只做 H5 字段读取、预览、统计和导出检查。当前不从前端生成 CSES 图件。

重要边界：

- 不修改 `<cluster_processed_root>` 中的 Cluster 原始处理程序和已有数据结构。
- 不把 CSES H5 原始文件复制进 Web 项目。
- 不把 CSES 接入正式 Cluster pipeline。
- 不在网页中运行 Cluster 多年生产重算。
- CSES 的磁场、轨道、质量、cadence 和频谱图件入口当前全部暂停。
- Cluster 频谱图保留；暂停的是 CSES 频谱图。
- 太阳风总览当前不在页面显示。

## 2. 启动方式

后端：

```bash
cd <repo>
PYTHONPATH=<repo>/backend \
  python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

前端：

```bash
cd <repo>/frontend
npm run dev
```

打开网页：

```text
http://127.0.0.1:5173/
```

健康检查：

```text
http://127.0.0.1:8000/api/health
```

如果网页打不开，先分别确认 `5173` 前端和 `8000` 后端是否都在运行。只开前端、后端掉线时，页面会出现 API down 或无法加载数据的状态。

## 3. 页面总体结构

页面采用复古科学控制台风格，主体由三块组成：

- 顶部栏：显示页面标题、数据源切换按钮和任务状态。
- 左侧档案栏：显示当前数据源的日期或文件列表。
- 右侧主工作区：显示数据上下文、处理日志、预览、统计、导出和图件生成区。

页面会随浏览器宽度变化：

- 宽屏时为左侧档案栏加右侧主工作区的双列布局。
- 中窄屏时自动收缩为单列布局。
- 当前已检查 1280、900、560 像素宽度，不应出现横向溢出。

## 4. 数据源切换

顶部有两个数据源按钮：

- `Cluster 频谱保留`
- `CSES 磁场实验`

点击按钮会切换整页的数据上下文。切换后，左侧文件列表、右侧可用功能、数据字段、预览范围和处理日志都会随数据源变化。

Cluster 和 CSES 的数据源逻辑是分开的。前端不会把同一套图件按钮硬套到两个数据源上。

## 5. Cluster 页面说明

### 5.1 数据来源

Cluster 页面读取已有处理产品，根目录为：

```text
<cluster_processed_root>
```

网页只读取已有数组并再生成 Web 自有 PNG，不运行原生产 pipeline，也不把旧 quicklook PNG/PDF 直接当作当前网页正式图件。

### 5.2 左侧档案栏

左侧显示 Cluster 日期档案。每个日期行会显示该日期已有产品数量，例如：

```text
2005-01-01  7/7 个产品
```

点击日期后，右侧会加载该日的元数据、变量信息、plot catalog 和上下文摘要。

### 5.3 顶部摘要

Cluster 主工作区顶部显示：

- 数据源状态。
- `daily_full` 键数和 compact 列数。
- 当前日期文件。
- 数据类型。

旧版的全局“能力”和“变量”两个大组件已从页面移除。

### 5.4 数据上下文

`数据上下文` 面板用于确认当前文件和范围，通常包括：

- 当前来源：Cluster。
- 当前日期文件。
- 数据类型。
- 当前选择变量。
- 当前范围。
- 已确认的时间字段、时间跨度、cadence 或采样率。
- 质量字段分布。
- 样本数和处理备注。

Cluster 的时间语义来自已处理产品，可作为 confirmed 信息使用。

### 5.5 处理日志

`处理日志` 面板记录当前页面请求和后端处理动作，例如：

- 读取文件列表。
- 读取 metadata。
- 读取 plot catalog。
- 生成图件。
- 导出或统计。

它是网页操作追踪，不等同于科学处理日志。

### 5.6 Cluster 图件目录

Cluster 当前页面显示 4 个图件：

- `磁场总览`
- `电场总览`
- `频谱总览`
- `轨道总览`

当前不显示：

- `太阳风总览`

图件按钮来自后端 plot catalog，但前端会过滤掉 solar wind 项。页面上没有太阳风总览入口。

### 5.7 Cluster 磁场总览

`磁场总览` 当前按 `<cluster_processed_root>/plot_daily_quicklook.py` 的 B quicklook 面板配方生成。

读取字段包括：

- `segment_B_GSE`
- `segment_B_MFA_after_delete`
- `segment_dB_MFA_detrended`
- `segment_dB_radial_psd`
- `segment_dB_phi_psd`
- `segment_dB_parallel_psd`
- `segment_sqrt_Br_band_power`
- `segment_sqrt_Bphi_band_power`
- `segment_sqrt_Bpar_band_power`
- `segment_time_context_unix`
- `segment_time_wavelet_unix`
- `segment_frequency_axis`
- `segment_L`
- `segment_MLT`
- `segment_MLAT`

生成图包含：

- GSE 磁场三分量。
- MFA 磁场三分量。
- detrended dB 三分量。
- radial / phi / parallel 三组 PSD。
- sqrt B band power。
- 底部 UTC、MLAT、MLT、L 辅助行。

这一步只使用已有 daily_full 数组，不在 Web 端重新计算 B 链、背景场、wavelet、band power 或坐标上下文。

输出目录：

```text
<repo>/outputs/generated_plots/cluster/
```

### 5.8 Cluster 频谱总览

`频谱总览` 保留。

它读取：

- `segment_dB_phi_psd`
- `segment_dE_phi_psd`
- `segment_frequency_axis`
- `segment_time_wavelet_unix`

并生成 B/E phi PSD 频谱面板。

频谱图色标当前对齐 `idlpython_v2/plot_daily_quicklook.py`：

- `LogNorm(vmin=1e-2, vmax=1e3)`
- `jet` colormap
- 低于下限颜色为黑色
- 频率轴单位为 Hz

注意：这是 Cluster 已处理产品的 Web 再生成图，不是 CSES 频谱图。

### 5.9 Cluster 电场总览

`电场总览` 从 `daily_full` 中读取已处理电场变量，例如 `segment_E_MFA`，生成电场 MFA 分量和模长的基础概览图。

它依赖已有处理产品，不在 Web 页面中重跑 EFW 处理流程。

### 5.10 Cluster 轨道总览

`轨道总览` 使用已处理上下文字段生成轨道相关面板，主要字段包括：

- `segment_MLT`
- `segment_MLAT`
- `segment_L`

它用于快速查看当前日期段的轨道上下文，不是新的轨道产品生成 pipeline。

### 5.11 Cluster 预览、统计和导出

Cluster 支持：

- 有界样本预览。
- 按 sample index 或已确认 UTC 范围裁剪。
- 统计输出。
- CSV、DAT、H5 导出。

CDF 导出当前保留为 TODO / reserved，不作为可用功能。

## 6. CSES HPM 页面说明

### 6.1 数据来源

CSES HPM 页面面向本机 H5 文件，当前常用根目录为：

```text
<local_cses_hpm_root>
```

H5 原始文件不会被复制到 Web 项目。网页依赖检查索引和按需读取结果。

CSES HPM 在当前网页中被视为：

```text
CSES-01 HPM magnetometer-only H5 datasource
```

也就是说，它不是 Cluster CDF 多仪器数据源。

### 6.2 当前状态

CSES 页面顶部明确显示：

```text
CSES HPM 图件入口暂停；当前只做 H5 draft 读取、字段预览、统计和导出检查。
```

并显示：

```text
DRAFT H5 INSPECTION / 字段读取检查
```

这表示当前 CSES 页面不生成科学图件。

### 6.3 暂停的 CSES 图件

当前前端不显示也不触发以下 CSES 作图按钮：

- HPM 磁场总览。
- HPM 质量总览。
- HPM 轨迹总览。
- HPM cadence 诊断。
- HPM 频谱图。
- HPM 电场图。
- HPM 太阳风图。
- 批量作图。

原因是：CSES HPM 时间语义、磁场变量、坐标字段、质量 flag、cadence 和后续筛选逻辑还没有达到正式图件入口要求。此前草稿检查或实验脚本生成的图，不属于当前网页正式功能。

### 6.4 左侧文件列表

CSES 左侧显示 H5 文件列表。每个文件行会显示：

- 文件名。
- 文件大小。
- inspection 状态。

点击文件后，右侧加载该文件的 H5 字段摘要、时间候选、质量字段和预览信息。

### 6.5 字段质量摘要

CSES 左侧仍保留一个轻量字段摘要区，用于选择可预览变量。它不是旧的全局“变量”组件，而是 H5 字段选择控件。

字段摘要通常显示：

- 字段路径，例如 `/B_FGM`、`/ALTITUDE`。
- shape。
- 推断单位。
- 状态，例如 GOOD / WARN。

这些信息来自 H5 inspection 和机械推断。凡是未由产品文档确认的字段语义，都应视为 inferred，不应写成最终科学事实。

### 6.6 CSES 数据范围

CSES 支持两种范围模式：

- `样本`：按 sample index 起止点读取。
- `UTC`：按机械解析的 `/UTC_TIME` 范围读取。

CSES `/UTC_TIME` 当前属于 inferred time semantics。它可以用于预览和检查，但在产品文档确认前，不应作为正式科学时间定义。

### 6.7 CSES 预览

选择字段和范围后，点击 `预览` 会请求后端读取有界样本，并显示表格。

预览用于确认：

- H5 文件能否读取。
- 字段 shape 是否符合预期。
- 时间和磁场字段是否能对齐。
- 数值是否有明显缺测或 fill value。

预览不是完整科学产品。

### 6.8 CSES 统计

CSES 支持单文件统计和多文件批量统计。

批量统计只做数值摘要，不生成批量图。当前页面没有 `批量作图` 按钮。

统计结果可保存为：

- JSON
- CSV
- DAT
- H5

### 6.9 CSES 导出

CSES 支持按选定字段和范围导出预览级数据。

可用格式：

- CSV
- DAT
- H5

导出结果写入：

```text
<repo>/outputs/exports/
```

每次导出同时生成 manifest，用于记录输入文件、变量、范围、格式和输出路径。

### 6.10 CSES 不支持项

当前 CSES 页面不支持：

- 电场分析。
- 太阳风上下文。
- 正式频谱图。
- Pc5 科学分析。
- MFA 坐标转换。
- 去背景场正式流程。
- 质量 flag 自动剔除。
- 多文件轨道拼接作图。
- 正式 plot catalog 上线。

这些功能需要字段语义、产品文档、质量控制规则和科学处理链进一步确认。

## 7. 输出目录

当前页面相关输出主要在：

```text
<repo>/outputs/
```

常见子目录：

- `outputs/generated_plots/cluster/`：Cluster Web 再生成 PNG。
- `outputs/exports/`：导出数据和 manifest。
- `outputs/stats/`：统计结果。
- `outputs/cses_hpm_inspection/`：CSES H5 inspection 结果。
- `outputs/cses_hpm_spectrogram_feasibility/`：此前 CSES 频谱可行性实验输出；它不是当前网页正式图件入口。

当前网页不会把输出写回：

```text
<local_cses_hpm_root>
```

## 8. API 与页面关系

页面主要依赖以下 API：

```text
GET  /api/health
GET  /api/datasources
GET  /api/datasources/{name}/files
GET  /api/datasources/{name}/metadata
GET  /api/datasources/{name}/variables
GET  /api/datasources/{name}/plot-catalog
POST /api/datasources/{name}/subset
POST /api/datasources/{name}/stats
POST /api/datasources/{name}/export
POST /api/datasources/cluster/plot
GET  /api/artifacts/{artifact_id}
```

当前页面只从前端触发 Cluster 作图。CSES 作图入口在前端暂停。

后端中可能仍有实验性或历史兼容接口，但本文档描述的是当前网页可见行为。不要把未在当前页面启用的 CSES 作图接口当成正式功能。

## 9. confirmed 与 inferred

页面和报告中应区分：

- `confirmed`：来自已有处理产品、已确认字段或直接可验证数据结构。
- `inferred`：根据变量名、数值范围或 inspection 结果推断。
- `unsupported`：该数据源不提供此类数据或当前不应启用。
- `unavailable`：理论上有该图件或字段要求，但当前文件缺少所需数组。

Cluster 已处理产品中的时间、PSD、MFA、轨道上下文字段通常按 confirmed 处理。

CSES HPM 的 `/UTC_TIME`、`/B_FGM`、位置字段和质量 flag 当前仍需要产品文档确认。它们可用于 draft inspection 和预览，不应在网页中作为正式科学结论。

## 10. 常见操作流程

### 10.1 查看 Cluster 频谱图

1. 打开网页。
2. 选择 `Cluster 频谱保留`。
3. 在左侧选择日期。
4. 在 `Cluster 再生成图` 中点击 `生成 频谱总览`。
5. 查看生成 PNG 和处理日志。

生成图保存在：

```text
outputs/generated_plots/cluster/
```

### 10.2 查看 Cluster 磁场总览

1. 选择 `Cluster 频谱保留`。
2. 选择日期。
3. 点击 `生成 磁场总览`。
4. 检查图件下方输出路径、来源产品、字段清单和处理日志。

处理日志中应能看到类似说明：

```text
Matched <cluster_processed_root>/plot_daily_quicklook.py B panel recipe.
Used stored arrays only; no B-chain, detrend, wavelet, band-power, or context values were recomputed.
```

### 10.3 预览 CSES H5 字段

1. 选择 `CSES 磁场实验`。
2. 左侧选择 H5 文件。
3. 在字段摘要中选择一个或多个字段。
4. 设置样本范围或 UTC 范围。
5. 点击 `预览`。

此流程只验证读取，不生成 CSES 图件。

### 10.4 导出 CSES 预览数据

1. 选择 CSES 文件。
2. 选择字段。
3. 设置范围。
4. 选择导出格式。
5. 点击 `导出结果`。

导出数据和 manifest 会写到：

```text
outputs/exports/
```

### 10.5 做 CSES 批量统计

1. 选择 `CSES 磁场实验`。
2. 选择主文件。
3. 在批量文件列表中勾选至少两个额外 H5 文件。
4. 选择统计范围和格式。
5. 点击 `批量统计`。

这只生成统计结果，不生成批量图。

## 11. 常见问题

### 11.1 页面打不开

检查前端：

```bash
lsof -nP -iTCP:5173 -sTCP:LISTEN
```

检查后端：

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN
```

如果后端没开，按本文第 2 节启动。

### 11.2 页面显示 API DOWN

通常是后端 `8000` 没启动，或前端代理无法访问后端。先访问：

```text
http://127.0.0.1:8000/api/health
```

### 11.3 Cluster 没有太阳风总览

这是当前预期行为。太阳风总览不在当前页面显示。当前 Cluster 图件入口只保留磁场、电场、频谱、轨道。

### 11.4 CSES 没有图件生成按钮

这是当前预期行为。CSES 图件入口已暂停，页面只做 H5 draft 读取、字段预览、统计和导出检查。

### 11.5 CSES 频谱图为什么没有

CSES 频谱目前只是做过 feasibility test，不是正式网页图件。时间语义、cadence、磁场变量和质量 masking 未经产品文档与处理链确认前，不启用 CSES 频谱入口。

### 11.6 Cluster 频谱图还在吗

在。Cluster 的 `频谱总览` 保留，并使用与 `idlpython_v2` 对齐的 PSD 色标。

## 12. 验证命令

后端测试：

```bash
cd <repo>
PYTHONPATH=backend python -m unittest backend.tests.test_cluster_datasource_api -v
```

前端测试：

```bash
cd <repo>/frontend
npm test -- --run
```

TypeScript 检查：

```bash
cd <repo>/frontend
npx tsc --noEmit
```

生产构建：

```bash
cd <repo>/frontend
npm run build
```

检查 Cluster 当前 plot catalog：

```bash
curl -s 'http://127.0.0.1:8000/api/datasources/cluster/plot-catalog?file_id=20051203' \
  | python -m json.tool
```

当前页面期望只显示以下 Cluster 图件：

```text
cluster_magnetic_overview
cluster_electric_overview
cluster_spectrogram_overview
cluster_orbit_overview
```

## 13. 科学边界提醒

当前网页适合做：

- 已有 Cluster 处理产品的本地浏览。
- Cluster Web 图件再生成。
- CSES H5 draft inspection。
- CSES 字段读取、预览、统计和导出验证。

当前网页不适合直接声称：

- 已完成 CSES Pc5 科学分析。
- 已确认 CSES HPM `/B_FGM` 可作为最终科学磁场变量。
- 已完成 CSES 频谱图上线。
- 已完成 CSES 坐标转换、背景场扣除、MFA 处理或模态识别。
- 已把 CSES 接入正式 Cluster pipeline。

对于 CSES，所有根据字段名或数值范围得到的判断，都应写作 inferred，并注明 requires product-document confirmation。
