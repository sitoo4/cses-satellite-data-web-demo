# 张衡一号 HPM 上传式分析页面说明

本文档说明当前 Web 页面版本。它是 CSES-01 HPM H5 文件的上传式诊断工具，不是正式科学处理流水线。

## 页面目标

当前页面只做以下事情：

- 上传一个或多个张衡一号 HPM H5 文件。
- 由后端读取 metadata、时间范围、样本数、质量标志和磁场字段可用性。
- 由后端按时间排序、去重、分段。
- 生成磁场图和可鼠标旋转的 3D 轨道图。
- 按当前裁剪时间范围导出 CSV、DAT 或 H5，并生成 manifest。
- 显示完整运行记录。

当前页面不做：

- 不从固定 HPM 数据目录或日期档案选择文件。
- 不在前端解析 H5 文件。
- 不生成 CSES 频谱图。
- 不做 STFT、wavelet、Pc5 科学分析。
- 不做电场图或太阳风总览。
- 不把上传文件写回原始数据目录。

## 使用流程

1. 启动后端和前端。
2. 打开 `http://127.0.0.1:5173`。
3. 点击页面顶部的 `上传文件`。
4. 选择一个或多个 `.h5` 文件。
5. 上传完成后查看页面顶部模式：
   - 1 个文件：`SINGLE FILE`
   - 2 个及以上文件：`BATCH`
6. 检查 `数据范围`、`裁剪区`、`运行记录`。
7. 选择 `磁场图` 或 `轨道图`。
8. 点击 `start!` 生成图像。
9. 需要导出时选择 `csv`、`dat` 或 `h5`，再点击导出区的 `start!`。

## 页面区域

### 顶部

顶部显示标题 `CSES HPM 数据分析`、上传按钮和当前模式。上传新文件会创建新 session，并清空旧图像和旧导出结果。

### 数据范围

数据范围只显示后端解析出的时间范围。它不再显示数据集树，也不让用户从历史日期里选择数据。

对于单文件，显示该文件的起止时间。

对于多文件，后端先按实际解析时间排序并去重，然后页面显示去重后的总时间范围和连续时间段数量。

### 裁剪区

裁剪区的时间来自后端可用时间范围。用户可以输入开始时间和结束时间。

如果选择范围跨过多个不连续时间段，后端只保留其中有数据的部分，绘图仍按 segment 分开显示。

如果选择范围内没有数据，后端返回不可用，前端显示错误提示。

如果 `/UTC_TIME` 无法解析，裁剪区会禁用。

### 图像按钮

当前只保留三个按钮：

- `磁场图`：可点击。
- `轨道图`：可点击。
- `频谱图`：保留但禁用。

频谱图禁用原因是：`频谱图暂未启用：当前 HPM 数据的时频分析规则尚未确认`。

### 图预览

未生成图像时显示 `图预览`。生成磁场图后显示 PNG；生成轨道图后显示交互式 HTML iframe。

### 导出

导出区域按当前裁剪范围导出数据。当前支持：

- CSV
- DAT
- H5

CDF 保留为 TODO，不生成文件。

每次导出都会生成 manifest，记录上传文件列表、裁剪范围、排序去重情况、segments、变量字段、导出格式和输出路径。

### 运行记录

运行记录是当前页面的重要组件。它显示：

- session id
- SINGLE FILE 或 BATCH
- 每个文件的文件名、起止时间、数据类型、文件大小、样本数
- 是否含三分量磁场或标量磁场
- 质量标志分布
- 后端排序后的文件顺序
- 重复文件数量
- 重复时间样本数量
- segment 列表
- warning 和 error
- 导出完成状态

## 后端逻辑

上传后，后端执行：

1. 保存上传文件到 `outputs/uploads/cses_hpm/<upload_session_id>/raw/`。
2. 用 `h5py` 读取 H5 文件。
3. 判断数据类型：
   - 文件名或字段指向 `HPM_5`：优先使用 `/B_FGM`。
   - 文件名或字段指向 `HPM_6`：优先使用 `/A211`。
4. 解析 `/UTC_TIME`。
5. 读取质量字段 `/FLAG_MT`、`/FLAG_SHW`、`/FLAG_TBB`、`/FLAG_N3` 中实际存在的字段。
6. 按解析时间排序。
7. 根据文件 hash 检测重复文件。
8. 根据时间戳去除重复样本。
9. 根据时间缺口切分连续 segment。
10. 生成 session metadata 和运行记录。

排序、去重和分段都在后端完成，前端不自行推断。

## 磁场图规则

`HPM_5` 单文件或同类型批量：

- 使用 `/B_FGM`。
- 画 Bx、By、Bz 和 `|B|`。
- 如果有多个不连续 segment，每个 segment 分开显示，避免在同一张时间轴上留下大片空白。

`HPM_6` 单文件或同类型批量：

- 使用 `/A211`。
- 画 scalar magnetic field。
- 不伪造三分量。

混合 `HPM_5` 和 `HPM_6`：

- 后端会提示混合数据类型。
- 当前不强行画成同一种图。

## 轨道图规则

轨道图是交互式 HTML，可用鼠标拖动旋转。

轨道图显示：

- 经纬度网格和标签。
- 左上角总起始时间和结束时间。
- 每个 segment 的起始时间和结束时间。
- 多个 segment 用不同颜色区分。

轨道颜色只表示 segment，不表示磁场大小。轨道图不显示 magnetic field colorbar。

## API 示例

上传单文件：

```bash
curl -s -X POST http://127.0.0.1:8000/api/cses-hpm/uploads \
  -F "files=@<local_cses_hpm_root>/demo_hpm_sample.h5"
```

生成磁场图：

```bash
curl -s -X POST http://127.0.0.1:8000/api/cses-hpm/uploads/<upload_session_id>/plot \
  -H 'Content-Type: application/json' \
  -d '{"plot_type":"magnetic"}'
```

生成轨道图：

```bash
curl -s -X POST http://127.0.0.1:8000/api/cses-hpm/uploads/<upload_session_id>/plot \
  -H 'Content-Type: application/json' \
  -d '{"plot_type":"orbit"}'
```

导出 CSV：

```bash
curl -s -X POST http://127.0.0.1:8000/api/cses-hpm/uploads/<upload_session_id>/export \
  -H 'Content-Type: application/json' \
  -d '{"format":"csv"}'
```

## 启动命令

后端：

```bash
cd <repo>
PYTHONPATH=<repo>/backend \
  python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

前端：

```bash
cd <repo>/frontend
npm install
npm run dev
```

## 测试场景

建议至少验证：

1. 上传单个 `HPM_5` 文件，生成磁场图和轨道图。
2. 上传两个完全相同的文件，确认运行记录显示重复文件或重复样本去重。
3. 先上传较晚时间文件，再上传较早时间文件，确认后端排序后页面显示正确总时间范围。
4. 上传中间有时间缺口的文件，确认磁场图和轨道图按多个 segment 展示。

## 已知限制

- 该页面是 diagnostic / feasibility 工具，不是正式科学产品。
- `/UTC_TIME` 的解析规则仍需要产品文档确认。
- `/B_FGM`、`/A211` 和质量标志含义仍需要产品文档确认。
- 混合 `HPM_5` 和 `HPM_6` 批量绘图暂不可用。
- CSES 频谱图暂未启用。
- CDF 导出暂未启用。
- 上传 session 暂存在本地输出目录，没有数据库和自动清理机制。
