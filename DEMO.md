# GitHub Pages Demo Guide

这个 demo 是静态展示版。页面打开后直接读取 `frontend/public/demo_data/` 中的脱敏派生文件，不启动后端，也不要求用户上传 H5。静态文件只包含降采样可视化数据和聚合统计，不包含原始 H5，也不包含完整逐点时间序列。

## 展示路线

1. 打开页面，说明当前是 `DEMO` 模式。
2. 看顶部标题、上传按钮和 disabled 频谱图按钮。
3. 点击上传按钮，页面提示：`当前为 demo，脱敏数据已准备，不支持上传`。
4. 看数据范围：页面展示预生成 demo 的北京时间范围、segment 数和样本数。
5. 看磁场图：默认展示 `magnetic_overview.png`。
6. 点击轨道图，再点击 `start!`，图预览区域切换为可旋转的 `orbit_demo.html`。
7. 看统计分析面板：展示 `B_abs`、位置范围和质量标志分布。
8. 在导出区域选择 csv/json/manifest，点击 export，下载预生成 demo 文件。
9. 打开运行记录，确认只显示：`当前为 demo，不提供运行日志服务`。

## 可展示功能

- 静态磁场总览图。
- 静态交互轨道图。
- 静态统计摘要。
- 降采样磁场和轨道展示数据。
- demo 统计结果下载。
- 频谱图禁用提示。

## 不展示功能

- H5 上传。
- 后端 API。
- 实时 H5 解析。
- 实时裁剪计算。
- 原始 H5 下载。
- 完整逐点 UTC_TIME、B_FGM 或逐点质量标志序列。
- STFT、wavelet、Pc5 PSD、正式科学事件识别。

## 本地预览

```bash
cd frontend
npm install
npm run dev
```

生产构建：

```bash
cd frontend
npm run build
```

如果 GitHub Pages 部署在仓库子路径：

```bash
cd frontend
VITE_BASE_PATH=/your-repo-name/ npm run build
```

## 讲解口径

这是一个 HPM 数据分析 Web Demo，重点展示上传驱动版本的前端设计和数据产品形态；公开版为了 GitHub Pages 可运行，预先把 H5 解析结果转成脱敏静态派生数据。demo 中的磁场和轨道展示点经过降采样，统计结果是聚合摘要。它不能替代正式科学处理流程，也不声称已经完成 Pc5 或频谱科学分析。
