import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Download, FileUp, Image as ImageIcon, Loader2, Play, Rotate3D, Save } from "lucide-react";

import { api, artifactDownloadUrl, artifactUrl, publicAssetUrl, type CropSelectDefault, type CropSelectOptions, type ExportPayload, type FeatureStatisticsPayload, type NumericStats, type PlotPayload, type SegmentRange, type UploadSessionPayload, type UploadedFileRecord } from "./api";

type PlotType = "magnetic" | "orbit" | "spectrogram";
type ExportFormat = "csv" | "dat" | "h5" | "cdf" | "json" | "manifest";
type CropSide = "start" | "end";

const IS_STATIC_DEMO = import.meta.env.VITE_DEMO_STATIC === "true";
const LOCAL_SPECTROGRAM_DISABLED_REASON = "频谱图暂未启用：当前 HPM 数据的时频分析规则尚未确认";
const STATIC_DEMO_NOTICE = "当前为 demo，脱敏数据已准备，不支持上传";
const STATIC_RUN_LOG_TEXT = "当前为 demo，不提供运行日志服务";
const STATIC_SPECTROGRAM_DISABLED_REASON = "涉及其他数据，demo 版本不支持展示";
const STATIC_CROP_DISABLED_REASON = "demo 版本不支持裁剪功能";
const STATIC_DOWNLOAD_DISABLED_REASON = "sorry！下载达咩哦";
const SPECTROGRAM_DISABLED_REASON = IS_STATIC_DEMO ? STATIC_SPECTROGRAM_DISABLED_REASON : LOCAL_SPECTROGRAM_DISABLED_REASON;

type StaticDemoSummary = {
  static_demo: boolean;
  mode: string;
  notice: string;
  session: UploadSessionPayload;
  plots: Record<"magnetic" | "orbit", NonNullable<PlotPayload["artifact"]>>;
  downloads: {
    statistics_json: NonNullable<FeatureStatisticsPayload["artifacts"]>["statistics_json"];
    statistics_summary_csv: NonNullable<FeatureStatisticsPayload["artifacts"]>["statistics_summary_csv"];
    manifest_json: NonNullable<FeatureStatisticsPayload["artifacts"]>["manifest_json"];
  };
};

export default function App() {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [staticSummary, setStaticSummary] = useState<StaticDemoSummary | null>(null);
  const [session, setSession] = useState<UploadSessionPayload | null>(null);
  const [plot, setPlot] = useState<PlotPayload | null>(null);
  const [statistics, setStatistics] = useState<FeatureStatisticsPayload | null>(null);
  const [exportResult, setExportResult] = useState<ExportPayload | null>(null);
  const [selectedPlot, setSelectedPlot] = useState<PlotType>("magnetic");
  const [exportFormat, setExportFormat] = useState<ExportFormat>("csv");
  const [cropStart, setCropStart] = useState<CropSelectDefault | null>(null);
  const [cropEnd, setCropEnd] = useState<CropSelectDefault | null>(null);
  const [loading, setLoading] = useState<"upload" | "plot" | "export" | "statistics" | "">("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!IS_STATIC_DEMO) {
      return;
    }
    let ignore = false;
    async function loadStaticDemo() {
      setLoading("upload");
      setError("");
      try {
        const [summaryResponse, statisticsResponse] = await Promise.all([
          fetch(publicAssetUrl("demo_data/demo_summary.json")),
          fetch(publicAssetUrl("demo_data/demo_statistics.json"))
        ]);
        if (!summaryResponse.ok || !statisticsResponse.ok) {
          throw new Error("静态 demo 数据缺失，请先运行 build_sanitized_static_demo.py");
        }
        const summary = (await summaryResponse.json()) as StaticDemoSummary;
        const stats = (await statisticsResponse.json()) as FeatureStatisticsPayload;
        if (ignore) {
          return;
        }
        setStaticSummary(summary);
        setSession(summary.session);
        setStatistics(stats);
        setCropStart(summary.session.crop_options?.start.default ?? null);
        setCropEnd(summary.session.crop_options?.end.default ?? null);
        setPlot(staticPlotPayload("magnetic", summary));
      } catch (err) {
        if (!ignore) {
          setError(errorMessage(err));
        }
      } finally {
        if (!ignore) {
          setLoading("");
        }
      }
    }
    void loadStaticDemo();
    return () => {
      ignore = true;
    };
  }, []);

  const modeLabel = IS_STATIC_DEMO ? "DEMO" : session ? (session.mode === "single" ? "SINGLE FILE" : "BATCH") : "READY";
  const cropDisabled = IS_STATIC_DEMO || !session?.crop_enabled;
  const runLog = useMemo(() => session?.run_log ?? [], [session]);

  async function uploadFiles(files: FileList | null) {
    if (IS_STATIC_DEMO) {
      setError(STATIC_DEMO_NOTICE);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      return;
    }
    const selected = Array.from(files ?? []).filter((file) => file.name.toLowerCase().endsWith(".h5"));
    if (!selected.length) {
      setError("请上传 H5 文件");
      return;
    }
    setLoading("upload");
    setError("");
    setPlot(null);
    setStatistics(null);
    setExportResult(null);
    try {
      const payload = await api.uploadCsesHpm(selected);
      setSession(payload);
      setCropStart(payload.crop_options?.start.default ?? null);
      setCropEnd(payload.crop_options?.end.default ?? null);
    } catch (err) {
      setError(errorMessage(err));
      setSession(null);
    } finally {
      setLoading("");
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  }

  async function startPlot() {
    if (!session) {
      setError("请先上传 H5 文件");
      return;
    }
    if (selectedPlot === "spectrogram") {
      setError(SPECTROGRAM_DISABLED_REASON);
      return;
    }
    if (IS_STATIC_DEMO) {
      setError("");
      if (!staticSummary) {
        setError("静态 demo 数据尚未加载完成");
        return;
      }
      setPlot(staticPlotPayload(selectedPlot, staticSummary));
      return;
    }
    setLoading("plot");
    setError("");
    setPlot(null);
    try {
      const payload = await api.plotUploadSession(session.upload_session_id, {
        plot_type: selectedPlot,
        crop_range: cropPayload()
      });
      setPlot(payload);
      await runStatistics(session.upload_session_id);
      if (payload.status !== "ok") {
        setError(payload.reason ?? "图像不可用");
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading("");
    }
  }

  async function runStatistics(sessionId: string) {
    setStatistics(null);
    const payload = await api.statisticsUploadSession(sessionId, {
      crop_range: cropPayload()
    });
    setStatistics(payload);
    try {
      const refreshed = await api.getUploadSession(sessionId);
      setSession(refreshed);
    } catch {
      // The statistics result is still usable even if the run-log refresh fails.
    }
  }

  async function exportData() {
    if (!session) {
      setError("请先上传 H5 文件");
      return;
    }
    if (IS_STATIC_DEMO) {
      setError(STATIC_DOWNLOAD_DISABLED_REASON);
      return;
    }
    setLoading("export");
    setError("");
    try {
      const payload = await api.exportUploadSession(session.upload_session_id, {
        format: exportFormat,
        crop_range: cropPayload()
      });
      setExportResult(payload);
      if (payload.status !== "ok") {
        setError(payload.reason ?? "导出不可用");
      } else if (payload.artifact?.artifact_id) {
        triggerArtifactDownload(payload.artifact);
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading("");
    }
  }

  function cropPayload() {
    if (!cropStart || !cropEnd) {
      return {};
    }
    return { start: beijingPartsToUtcIso(cropStart), end: beijingPartsToUtcIso(cropEnd) };
  }

  function updateCrop(side: CropSide, patch: Partial<CropSelectDefault>) {
    const current = side === "start" ? cropStart : cropEnd;
    const next = normalizeCropParts({ ...(current ?? defaultCropParts()), ...patch }, session?.crop_options?.[side]);
    if (side === "start") {
      setCropStart(next);
    } else {
      setCropEnd(next);
    }
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="mascot mascot-left">
          <img src={publicAssetUrl("mascots/theme-main.png")} alt="" />
        </div>
        <h1>CSES HPM 数据分析</h1>
        {IS_STATIC_DEMO ? (
          <button className="upload-button" type="button" title={STATIC_DEMO_NOTICE} onClick={() => setError(STATIC_DEMO_NOTICE)}>
            <FileUp size={19} aria-hidden="true" />
            上传文件
          </button>
        ) : (
          <label className="upload-button">
            <FileUp size={19} aria-hidden="true" />
            上传文件
            <input
              ref={fileInputRef}
              aria-label="上传文件"
              type="file"
              multiple
              accept=".h5,.hdf5"
              onChange={(event) => void uploadFiles(event.target.files)}
            />
          </label>
        )}
        <div className="mode-badge">{modeLabel}</div>
        <div className="mascot-strip" aria-hidden="true">
          <img className="mascot-strip-image mascot-3" src={publicAssetUrl("mascots/theme-3.png")} alt="" />
          <img className="mascot-strip-image mascot-5" src={publicAssetUrl("mascots/theme-5.png")} alt="" />
          <img className="mascot-strip-image mascot-6" src={publicAssetUrl("mascots/theme-6.png")} alt="" />
          <img className="mascot-strip-image mascot-7" src={publicAssetUrl("mascots/theme-7.png")} alt="" />
        </div>
      </header>

      {error ? <div className="notice" role="alert">{error}</div> : null}

      <section className="console-frame">
        <section className="control-row">
          <div className="label-cell range-label-cell">数据<br />范围</div>
          <div className="range-box">
            {session ? (
              <>
                <div className="range-line">
                  <strong>{session.display_time_range?.start ?? session.merged_time_range.start ?? "时间不可解析"}</strong>
                  <span>至</span>
                </div>
                <div className="range-line">
                  <strong>{session.display_time_range?.end ?? session.merged_time_range.end ?? "时间不可解析"}</strong>
                </div>
                <small>
                  <span className="range-meta-line">{session.segments.length} 个连续时间段 · {session.plot_groups?.length ?? session.segments.length} 个绘图组</span>
                  <span className="range-meta-line">去重后 {session.sample_count} 个样本 · 北京时间</span>
                </small>
              </>
            ) : (
              <span>上传 H5 文件后显示后端解析的时间范围</span>
            )}
          </div>
          <div className="label-cell crop-label-cell" title={IS_STATIC_DEMO ? STATIC_CROP_DISABLED_REASON : undefined}>
            <strong>裁剪区</strong>
            <small>
              <span>裁剪范围为可用时间段</span>
              <span>按北京时间选择</span>
            </small>
          </div>
          <div className="crop-box">
            {session?.crop_options && cropStart && cropEnd ? (
              <CropRangeSelector
                disabled={cropDisabled}
                start={cropStart}
                end={cropEnd}
                startOptions={session.crop_options.start}
                endOptions={session.crop_options.end}
                onChange={updateCrop}
              />
            ) : null}
            <div className="crop-export-row" title={IS_STATIC_DEMO ? STATIC_DOWNLOAD_DISABLED_REASON : undefined}>
              <span className="crop-export-label">{IS_STATIC_DEMO ? "下载 demo 统计结果" : "按当前裁剪后的数据范围导出"}</span>
              <select value={exportFormat} onChange={(event) => setExportFormat(event.target.value as ExportFormat)}>
                {IS_STATIC_DEMO ? (
                  <>
                    <option value="csv">csv</option>
                    <option value="dat">dat</option>
                    <option value="h5">h5</option>
                  </>
                ) : (
                  <>
                    <option value="csv">csv</option>
                    <option value="dat">dat</option>
                    <option value="h5">h5</option>
                    <option value="cdf" disabled>cdf TODO</option>
                  </>
                )}
              </select>
              <button type="button" title={IS_STATIC_DEMO ? STATIC_DOWNLOAD_DISABLED_REASON : undefined} disabled={IS_STATIC_DEMO} onClick={() => void exportData()}>
                {loading === "export" ? <Loader2 size={16} aria-hidden="true" /> : <Save size={16} aria-hidden="true" />}
                export
              </button>
            </div>
          </div>
          <button className="start-button" type="button" onClick={() => void startPlot()}>
            {loading === "plot" ? <Loader2 size={18} aria-hidden="true" /> : <Play size={18} aria-hidden="true" />}
            start!
          </button>
        </section>

        <section className="preview-shell">
          <div className="plot-buttons" aria-label="图像类型">
            <button className={selectedPlot === "magnetic" ? "selected" : ""} type="button" onClick={() => setSelectedPlot("magnetic")}>
              <ImageIcon size={16} aria-hidden="true" />
              磁场图
            </button>
            <button className={selectedPlot === "orbit" ? "selected" : ""} type="button" onClick={() => setSelectedPlot("orbit")}>
              <Rotate3D size={16} aria-hidden="true" />
              轨道图
            </button>
            <button type="button" disabled title={SPECTROGRAM_DISABLED_REASON}>
              频谱图
            </button>
          </div>
          <div className="preview-area">
            <FeatureStatisticsPanel statistics={statistics} loading={loading === "plot" || loading === "statistics"} />
            <div className="plot-preview-stage">
              {plot?.status === "ok" && plot.artifact ? <PlotArtifact plot={plot} /> : <strong>图预览</strong>}
              {plot?.artifact && !IS_STATIC_DEMO ? (
                <a className="plot-download-button" href={artifactDownloadHref(plot.artifact)} download>
                  <Download size={15} aria-hidden="true" />
                  导出当前图像
                </a>
              ) : null}
            </div>
          </div>
        </section>

        <section className="bottom-row">
          <RunLogPanel session={session} runLog={runLog} exportResult={exportResult} staticDemo={IS_STATIC_DEMO} />
        </section>
      </section>
    </main>
  );
}

function PlotArtifact({ plot }: { plot: PlotPayload }) {
  if (!plot.artifact) {
    return null;
  }
  const url = artifactHref(plot.artifact);
  if (plot.artifact.media_type === "text/html") {
    return <iframe className="plot-frame" src={url} title="交互轨道图" />;
  }
  return <img className="plot-image" src={url} alt={plot.artifact.label ?? "生成图像"} />;
}

function FeatureStatisticsPanel({ statistics, loading }: { statistics: FeatureStatisticsPayload | null; loading: boolean }) {
  const magnetic = statistics?.overall_statistics.magnetic;
  const magneticVariables = magnetic?.variables ?? {};
  const primaryMagnetic = magneticVariables.B_abs ?? magneticVariables.scalar_B;
  const positionVariables = statistics?.overall_statistics.position?.variables ?? {};
  const quality = statistics?.quality_flag_statistics ?? statistics?.overall_statistics.quality_flags ?? {};
  return (
    <aside className="statistics-panel">
      <h2>统计分析</h2>
      {!statistics ? (
        <p className="statistics-empty">{loading ? "统计生成中..." : "点击 start 后按当前裁剪范围统计去重排序后的数据"}</p>
      ) : (
        <>
          <div className="statistics-grid">
            <StatItem
              className="time-range-stat"
              label="时间范围"
              value={
                <span className="time-range-stat-lines">
                  <span>{statistics.time_range.display_start_time ?? statistics.time_range.start_time ?? "-"}</span>
                  <span>{statistics.time_range.display_end_time ?? statistics.time_range.end_time ?? "-"}</span>
                </span>
              }
            />
            <StatItem label="样本数" value={String(statistics.processing_summary.final_sample_count)} />
            <StatItem label="Segment" value={String(statistics.processing_summary.segment_count)} />
            <StatItem label="样本去重" value={String(statistics.processing_summary.duplicate_time_removed_count)} />
            <StatItem label="采样中位数" value={numberLabel(statistics.overall_statistics.sampling?.cadence_median_seconds, "s")} />
            <StatItem label="数据类型" value={displayProductType(statistics.product_type_status)} />
          </div>
          {primaryMagnetic ? (
            <div className="statistics-block magnetic-statistics-block">
              <strong>{magneticVariables.B_abs ? "B_abs" : "scalar_B"}</strong>
              <table className="statistics-table" aria-label={`${magneticVariables.B_abs ? "B_abs" : "scalar_B"}统计表`}>
                <tbody>
                  {[
                    ["min", numberLabel(primaryMagnetic.min, primaryMagnetic.unit)],
                    ["max", numberLabel(primaryMagnetic.max, primaryMagnetic.unit)],
                    ["mean", numberLabel(primaryMagnetic.mean, primaryMagnetic.unit)],
                    ["median", numberLabel(primaryMagnetic.median, primaryMagnetic.unit)],
                    ["std", numberLabel(primaryMagnetic.std, primaryMagnetic.unit)]
                  ].map(([label, value]) => (
                    <tr key={label}>
                      <th scope="row">{label}</th>
                      <td>{value}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : magnetic?.reason ? (
            <p className="statistics-warning">{magnetic.reason}</p>
          ) : null}
          <div className="statistics-block compact">
            <strong>位置范围</strong>
            <table className="statistics-table position-statistics-table" aria-label="位置范围统计表">
              <tbody>
                {["GEO_LAT", "GEO_LON", "ALTITUDE"].map((name) => {
                  const stats = positionVariables[name];
                  return (
                    <tr key={name}>
                      <th scope="row">{name}</th>
                      <td>
                        {stats?.status === "missing" ? (
                          "missing"
                        ) : (
                          <span className="position-range-pairs">
                            {positionRangeItems(stats?.min, stats?.max, stats?.unit).map((item) => (
                              <span className="position-range-pair" key={item.label}>
                                <span className="position-range-key">{item.label}：</span>
                                <span className="position-range-value">{item.value}</span>
                              </span>
                            ))}
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="statistics-block compact">
            <strong>质量标志</strong>
            <table className="statistics-table quality-statistics-table" aria-label="质量标志统计表">
              <tbody>
                {Object.entries(quality).map(([field, summary]) => (
                  <tr key={field}>
                    <th scope="row"><span>{field}</span><small>{qualityFlagFieldLabel(field)}</small></th>
                    <td>
                      {summary.status === "missing" ? (
                        "missing"
                      ) : (
                        <span className="quality-count-lines">
                          {formatQualityFlagCountItems(field, summary.value_counts).map((item) => (
                            <span key={item}>{item}</span>
                          ))}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="statistics-downloads" title={IS_STATIC_DEMO ? STATIC_DOWNLOAD_DISABLED_REASON : undefined}>
            {statistics.artifacts?.statistics_json ? <DownloadControl href={artifactDownloadHref(statistics.artifacts.statistics_json)} label="导出统计 JSON" /> : null}
            {statistics.artifacts?.statistics_summary_csv ? <DownloadControl href={artifactDownloadHref(statistics.artifacts.statistics_summary_csv)} label="导出统计 CSV" /> : null}
          </div>
          {statistics.warnings.length ? <p className="statistics-warning">warning: {statistics.warnings.join("; ")}</p> : null}
        </>
      )}
    </aside>
  );
}

function DownloadControl({ href, label }: { href: string; label: string }) {
  if (IS_STATIC_DEMO) {
    return (
      <span className="download-disabled" title={STATIC_DOWNLOAD_DISABLED_REASON}>
        {label}
      </span>
    );
  }
  return <a href={href} download>{label}</a>;
}

function StatItem({ label, value, className = "" }: { label: string; value: ReactNode; className?: string }) {
  return (
    <div className={className}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function displayProductType(productTypeStatus: FeatureStatisticsPayload["product_type_status"]): string {
  const productType = productTypeStatus.product_type ?? productTypeStatus.products?.join("/");
  return productType ? productType.replaceAll("_", "") : productTypeStatus.status;
}

function numberLabel(value: NumericStats[keyof NumericStats] | number | null | undefined, unit?: string | null): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "-";
  }
  const formatted = Math.abs(value) >= 100 ? value.toFixed(1) : value.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
  return unit ? `${formatted} ${unit}` : formatted;
}

function rangeLabel(min: NumericStats[keyof NumericStats] | number | null | undefined, max: NumericStats[keyof NumericStats] | number | null | undefined, unit?: string | null): string {
  return `${numberLabel(min, unit)} 至 ${numberLabel(max, unit)}`;
}

function positionValueLabel(value: NumericStats[keyof NumericStats] | number | null | undefined, unit?: string | null): string {
  const formatted = numberLabel(value);
  return unit ? `${formatted}${unit}` : formatted;
}

function positionRangeItems(min: NumericStats[keyof NumericStats] | number | null | undefined, max: NumericStats[keyof NumericStats] | number | null | undefined, unit?: string | null): Array<{ label: string; value: string }> {
  return [
    { label: "始", value: positionValueLabel(min, unit) },
    { label: "终", value: positionValueLabel(max, unit) }
  ];
}

function formatQualityFlagCounts(field: string, counts: Record<string, number>): string {
  return formatQualityFlagCountItems(field, counts).join(", ");
}

function formatQualityFlagCountItems(field: string, counts: Record<string, number>): string[] {
  return Object.entries(counts).map(([value, count]) => `${qualityFlagValueLabel(field, value)}=${count}`);
}

function qualityFlagValueLabel(field: string, value: string): string {
  const labels: Record<string, Record<string, string>> = {
    "/FLAG_MT": { "0": "未标记", "1": "磁力矩器干扰标记" },
    "/FLAG_SHW": { "0": "未触发", "1": "触发" },
    "/FLAG_TBB": { "0": "未触发", "1": "触发" },
    "/FLAG_N3": { "0": "未标记", "1": "已标记" }
  };
  return labels[field]?.[value] ?? `值 ${value}`;
}

function qualityFlagFieldLabel(field: string): string {
  const labels: Record<string, string> = {
    "/FLAG_MT": "磁力矩器干扰标志",
    "/FLAG_SHW": "地影/日照状态",
    "/FLAG_TBB": "TBB 开关状态",
    "/FLAG_N3": "N3 标志"
  };
  return labels[field] ?? "质量标志";
}

function artifactHref(artifact: { artifact_id: string; url?: string }): string {
  return artifact.url ? publicAssetUrl(artifact.url) : artifactUrl(artifact.artifact_id);
}

function artifactDownloadHref(artifact: { artifact_id: string; url?: string; download_url?: string }): string {
  if (artifact.download_url) {
    return publicAssetUrl(artifact.download_url);
  }
  if (artifact.url) {
    return publicAssetUrl(artifact.url);
  }
  return artifactDownloadUrl(artifact.artifact_id);
}

function staticPlotPayload(plotType: "magnetic" | "orbit", summary: StaticDemoSummary): PlotPayload {
  return {
    upload_session_id: summary.session.upload_session_id,
    plot_type: plotType,
    status: "ok",
    segments: summary.session.segments,
    artifact: summary.plots[plotType]
  };
}

function triggerArtifactDownload(artifact: { artifact_id: string; url?: string; download_url?: string }) {
  const link = document.createElement("a");
  link.href = artifactDownloadHref(artifact);
  link.download = "";
  link.style.display = "none";
  document.body.appendChild(link);
  link.click();
  link.remove();
}

function CropRangeSelector({
  disabled,
  start,
  end,
  startOptions,
  endOptions,
  onChange
}: {
  disabled: boolean;
  start: CropSelectDefault;
  end: CropSelectDefault;
  startOptions: CropSelectOptions;
  endOptions: CropSelectOptions;
  onChange: (side: CropSide, patch: Partial<CropSelectDefault>) => void;
}) {
  return (
    <div className="crop-selectors">
      <CropSelector label="开始" side="start" value={start} options={startOptions} disabled={disabled} onChange={onChange} />
      <CropSelector label="结束" side="end" value={end} options={endOptions} disabled={disabled} onChange={onChange} />
    </div>
  );
}

function CropSelector({
  label,
  side,
  value,
  options,
  disabled,
  onChange
}: {
  label: string;
  side: CropSide;
  value: CropSelectDefault;
  options: CropSelectOptions;
  disabled: boolean;
  onChange: (side: CropSide, patch: Partial<CropSelectDefault>) => void;
}) {
  const slots = timeSlotsFromOptions(options);
  const yearOptions = uniqueNumbers(slots.map((slot) => slot.year));
  const monthOptions = uniqueNumbers(slots.filter((slot) => slot.year === value.year).map((slot) => slot.month));
  const dayOptions = uniqueNumbers(slots.filter((slot) => slot.year === value.year && slot.month === value.month).map((slot) => slot.day));
  const hourOptions = uniqueNumbers(slots.filter((slot) => slot.year === value.year && slot.month === value.month && slot.day === value.day).map((slot) => slot.hour));
  const minuteOptions = slots.find((slot) => slot.year === value.year && slot.month === value.month && slot.day === value.day && slot.hour === value.hour)?.minutes ?? [value.minute];
  return (
    <div className="crop-selector" role="group" aria-label={`${label}时间`}>
      <span className="crop-row-title">{label}</span>
      <LabeledSelect label={`${label}年`} value={value.year} options={yearOptions} disabled={disabled} onChange={(next) => onChange(side, { year: next })} />
      <LabeledSelect label={`${label}月`} value={value.month} options={monthOptions} disabled={disabled} pad onChange={(next) => onChange(side, { month: next })} />
      <LabeledSelect label={`${label}日`} value={value.day} options={dayOptions} disabled={disabled} pad onChange={(next) => onChange(side, { day: next })} />
      <LabeledSelect label={`${label}时`} value={value.hour} options={hourOptions} disabled={disabled} pad onChange={(next) => onChange(side, { hour: next })} />
      <LabeledSelect label={`${label}分`} value={value.minute} options={minuteOptions} disabled={disabled} pad onChange={(next) => onChange(side, { minute: next })} />
    </div>
  );
}

function LabeledSelect({ label, value, options, disabled, pad = false, onChange }: { label: string; value: number; options: number[]; disabled: boolean; pad?: boolean; onChange: (value: number) => void }) {
  const normalized = options.length ? options : [value];
  return (
    <label>
      <span>{label.slice(-1)}</span>
      <select aria-label={label} value={value} disabled={disabled} onChange={(event) => onChange(Number(event.target.value))}>
        {normalized.map((item) => (
          <option key={item} value={item}>
            {pad ? item.toString().padStart(2, "0") : item}
          </option>
        ))}
      </select>
    </label>
  );
}

function RunLogPanel({ session, runLog, exportResult, staticDemo }: { session: UploadSessionPayload | null; runLog: string[]; exportResult: ExportPayload | null; staticDemo: boolean }) {
  if (staticDemo) {
    return (
      <section className="run-log-panel">
        <h2>运行记录</h2>
        <p className="empty-log">{STATIC_RUN_LOG_TEXT}</p>
        {exportResult?.status === "ok" ? <p className="empty-log">demo 统计结果已准备下载：{exportResult.format}</p> : null}
      </section>
    );
  }
  return (
    <section className="run-log-panel">
      <h2>运行记录</h2>
      {session ? (
        <>
          <div className="session-summary">
            <strong>{session.mode === "single" ? "SINGLE FILE" : "BATCH"}</strong>
            <span>session: {session.upload_session_id}</span>
            <span>重复文件 {session.dedupe.duplicate_file_count} · 重复样本 {session.dedupe.duplicate_sample_count}</span>
          </div>
          <div className="segment-list">
            {(session.plot_groups?.length ? session.plot_groups : session.segments).map((segment) => (
              <p key={"group_id" in segment ? segment.group_id : segment.segment_id}>
                <strong>{"group_id" in segment ? segment.group_id : segment.segment_id}</strong>
                <span>{"display_start" in segment && segment.display_start ? `${segment.display_start} - ${segment.display_end}` : `${segment.start} - ${segment.end}`}</span>
              </p>
            ))}
          </div>
          <div className="sorted-files">
            <strong>后端排序后的文件顺序</strong>
            {session.sorted_files.map((item, index) => (
              <p key={`${item.upload_id}-${index}`}>
                {index + 1}. {item.filename} · {item.display_start ?? item.start ?? "-"} - {item.display_end ?? item.end ?? "-"}
              </p>
            ))}
          </div>
          <div className="file-records">
            {session.per_file_records.map((record) => <FileRecordCard key={record.upload_id} record={record} />)}
          </div>
          <div className="action-log">
            {runLog.map((line, index) => <p key={`${line}-${index}`}>{line}</p>)}
            {exportResult?.status === "ok" ? <p>导出完成：{exportResult.format.toUpperCase()} · {exportResult.row_count} 行 · manifest 已生成</p> : null}
          </div>
        </>
      ) : (
        <p className="empty-log">上传文件后显示每个文件的解析记录、质量标志、排序去重和 warning/error。</p>
      )}
    </section>
  );
}

function defaultCropParts(): CropSelectDefault {
  return { year: 1970, month: 1, day: 1, hour: 0, minute: 0 };
}

function normalizeCropParts(value: CropSelectDefault, options: CropSelectOptions | undefined): CropSelectDefault {
  if (!options) {
    return value;
  }
  const slots = timeSlotsFromOptions(options);
  const year = nearestOption(value.year, uniqueNumbers(slots.map((slot) => slot.year)));
  const month = nearestOption(value.month, uniqueNumbers(slots.filter((slot) => slot.year === year).map((slot) => slot.month)));
  const day = nearestOption(value.day, uniqueNumbers(slots.filter((slot) => slot.year === year && slot.month === month).map((slot) => slot.day)));
  const hour = nearestOption(value.hour, uniqueNumbers(slots.filter((slot) => slot.year === year && slot.month === month && slot.day === day).map((slot) => slot.hour)));
  const minutes = slots.find((slot) => slot.year === year && slot.month === month && slot.day === day && slot.hour === hour)?.minutes ?? [value.minute];
  const minute = nearestOption(value.minute, minutes);
  return { year, month, day, hour, minute };
}

function timeSlotsFromOptions(options: CropSelectOptions): Array<CropSelectDefault & { minutes: number[] }> {
  const slots = Object.entries(options.minutes_by_hour).map(([key, minutes]) => {
    const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2})$/.exec(key);
    if (!match) {
      return null;
    }
    return {
      year: Number(match[1]),
      month: Number(match[2]),
      day: Number(match[3]),
      hour: Number(match[4]),
      minute: minutes[0] ?? 0,
      minutes
    };
  }).filter((item): item is CropSelectDefault & { minutes: number[] } => item !== null);
  if (slots.length) {
    return slots;
  }
  return options.hours.map((hour) => ({
    year: options.default?.year ?? options.years[0] ?? 1970,
    month: options.default?.month ?? options.months[0] ?? 1,
    day: options.default?.day ?? options.days[0] ?? 1,
    hour,
    minute: 0,
    minutes: options.minutes_by_hour[String(hour)] ?? [0]
  }));
}

function uniqueNumbers(values: number[]): number[] {
  return Array.from(new Set(values)).sort((a, b) => a - b);
}

function nearestOption(value: number, options: number[]): number {
  if (!options.length) {
    return value;
  }
  if (options.includes(value)) {
    return value;
  }
  return options.reduce((best, item) => (Math.abs(item - value) < Math.abs(best - value) ? item : best), options[0]);
}

function beijingPartsToUtcIso(value: CropSelectDefault): string {
  const utcMillis = Date.UTC(value.year, value.month - 1, value.day, value.hour - 8, value.minute, 0, 0);
  return new Date(utcMillis).toISOString().replace(".000Z", "Z");
}

function FileRecordCard({ record }: { record: UploadedFileRecord }) {
  return (
    <article className="file-card">
      <h3>{record.filename}</h3>
      <dl>
        <div><dt>类型</dt><dd>{record.hpm_product}</dd></div>
        <div><dt>大小</dt><dd>{bytesLabel(record.size_bytes)}</dd></div>
        <div><dt>样本</dt><dd>{record.sample_count}</dd></div>
        <div><dt>起始</dt><dd>{record.display_start_time ?? record.start_time ?? "-"} 北京时间</dd></div>
        <div><dt>结束</dt><dd>{record.display_end_time ?? record.end_time ?? "-"} 北京时间</dd></div>
        <div><dt>磁场</dt><dd>{record.has_vector_magnetic ? "三分量" : record.has_scalar_magnetic ? "标量" : "不可用"}</dd></div>
      </dl>
      <div className="flag-lines">
        {Object.entries(record.quality_flag_summary).map(([field, summary]) => (
          <span key={field}>{field}: {formatQualityFlagCounts(field, summary.distribution)}</span>
        ))}
      </div>
      {record.duplicate_of ? <p className="warn-line">重复文件：{record.duplicate_of}</p> : null}
      {record.warnings.map((warning) => <p className="warn-line" key={warning}>{warning}</p>)}
      {record.errors.map((err) => <p className="error-line" key={err}>{err}</p>)}
    </article>
  );
}

function bytesLabel(bytes: number | undefined): string {
  if (!bytes || bytes <= 0) {
    return "0 B";
  }
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value >= 10 || unit === 0 ? value.toFixed(0) : value.toFixed(1)} ${units[unit]}`;
}

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}
