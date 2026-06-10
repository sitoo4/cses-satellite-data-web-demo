import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";

function uploadPayload(fileCount: number) {
  return {
    upload_session_id: fileCount === 1 ? "single-session" : "batch-session",
    mode: fileCount === 1 ? "single" : "batch",
    created_at: "2026-06-08T00:00:00Z",
    per_file_records: Array.from({ length: fileCount }, (_, index) => ({
      upload_id: `file_${index + 1}`,
      filename: `demo_upload_${index + 1}.h5`,
      size_bytes: 2048,
      duplicate_of: index === 1 && fileCount === 2 ? "demo_upload_1.h5" : null,
      status: "ok",
      hpm_product: "HPM_5",
      sample_count: 4,
      time_parseable: true,
      start_time: index === 0 ? "2023-04-19T23:55:00Z" : "2023-04-20T00:00:00Z",
      end_time: index === 0 ? "2023-04-19T23:55:03Z" : "2023-04-20T00:00:03Z",
      display_start_time: index === 0 ? "2023-04-20 07:55" : "2023-04-20 08:00",
      display_end_time: index === 0 ? "2023-04-20 07:55" : "2023-04-20 08:00",
      has_vector_magnetic: true,
      has_scalar_magnetic: false,
      quality_flag_summary: { "/FLAG_MT": { distribution: { "0": 2, "1": 2 }, sample_count: 4 } },
      warnings: [],
      errors: []
    })),
    sorted_files: [
      {
        upload_id: "file_1",
        filename: "demo_upload_1.h5",
        hpm_product: "HPM_5",
        start: "2023-04-19T23:55:00Z",
        end: "2023-04-19T23:55:03Z",
        display_start: "2023-04-20 07:55",
        display_end: "2023-04-20 07:55"
      }
    ],
    merged_time_range: { start: "2023-04-19T23:55:00Z", end: "2023-04-20T00:00:03Z" },
    display_time_zone: "Asia/Shanghai",
    display_time_range: { start: "2023-04-20 07:55", end: "2023-04-20 08:00" },
    crop_options: {
      start: {
        years: [2023],
        months: [4],
        days: [20],
        hours: [7, 8],
        minutes_by_hour: { "7": [55, 56, 57, 58, 59], "8": [0] },
        default: { year: 2023, month: 4, day: 20, hour: 7, minute: 55 }
      },
      end: {
        years: [2023],
        months: [4],
        days: [20],
        hours: [7, 8],
        minutes_by_hour: { "7": [55, 56, 57, 58, 59], "8": [0] },
        default: { year: 2023, month: 4, day: 20, hour: 8, minute: 0 }
      }
    },
    segments: [
      { segment_id: "segment_1", start: "2023-04-19T23:55:00Z", end: "2023-04-19T23:55:03Z", sample_count: 4 },
      { segment_id: "segment_2", start: "2023-04-20T00:00:00Z", end: "2023-04-20T00:00:03Z", sample_count: 4 }
    ].slice(0, fileCount === 1 ? 1 : 2),
    plot_groups: [
      { group_id: "group_1", start: "2023-04-19T23:55:00Z", end: "2023-04-20T00:00:03Z", display_start: "2023-04-20 07:55", display_end: "2023-04-20 08:00", segment_ids: ["segment_1"], reason: "same_beijing_day_or_gap_lt_60min" }
    ],
    sample_count: fileCount === 1 ? 4 : 4,
    raw_sample_count: fileCount === 1 ? 4 : 8,
    dedupe: { duplicate_file_count: fileCount === 2 ? 1 : 0, duplicate_sample_count: fileCount === 2 ? 4 : 0 },
    data_products: ["HPM_5"],
    time_parseable: true,
    crop_enabled: true,
    quality_flag_summary: { "/FLAG_MT": { distribution: { "0": 2, "1": 2 } } },
    run_log: fileCount === 1 ? ["解析成功", "时间排序完成", "分段数量: 1"] : ["解析成功", "时间排序完成", "重复文件去除: 1 个", "重复时间样本去除: 4 个", "分段数量: 2"]
  };
}

function staticUploadPayload() {
  const payload = uploadPayload(2);
  return {
    ...payload,
    upload_session_id: "static-public-demo",
    crop_enabled: false,
    run_log: [],
    display_time_range: { start: "2000-12-17 07:55", end: "2000-12-17 08:00" },
    crop_options: {
      start: { ...payload.crop_options.start, years: [2000], months: [12], days: [17], default: { year: 2000, month: 12, day: 17, hour: 7, minute: 55 }, minutes_by_hour: { "2000-12-17T07": [55] } },
      end: { ...payload.crop_options.end, years: [2000], months: [12], days: [17], default: { year: 2000, month: 12, day: 17, hour: 8, minute: 0 }, minutes_by_hour: { "2000-12-17T08": [0] } }
    }
  };
}

describe("App upload workflow", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url === "/api/cses-hpm/uploads" && init?.method === "POST") {
          const form = init.body as FormData;
          const fileCount = form.getAll("files").length;
          return jsonResponse(uploadPayload(fileCount));
        }
        if (url.includes("/api/cses-hpm/uploads/") && init?.method === undefined) {
          return jsonResponse(uploadPayload(url.includes("batch") ? 2 : 1));
        }
        if (url.includes("/plot")) {
          const body = JSON.parse(String(init?.body));
          return jsonResponse({
            upload_session_id: "single-session",
            plot_type: body.plot_type,
            status: "ok",
            artifact: {
              artifact_id: body.plot_type === "orbit" ? "orbit-html" : "magnetic-png",
              media_type: body.plot_type === "orbit" ? "text/html" : "image/png",
              label: "plot"
            }
          });
        }
        if (url.includes("/statistics")) {
          return jsonResponse({
            session_id: "single-session",
            product_type_status: { status: "single", products: ["HPM_5"], product_type: "HPM_5" },
            time_range: {
              start_time: "2023-04-19T23:55:00Z",
              end_time: "2023-04-19T23:55:03Z",
              display_start_time: "2023-04-20 07:55",
              display_end_time: "2023-04-20 07:55"
            },
            processing_summary: {
              uploaded_file_count: 1,
              unique_file_count: 1,
              duplicate_file_count: 0,
              raw_sample_count: 4,
              merged_sample_count: 4,
              duplicate_time_removed_count: 0,
              sorted_by_time: true,
              dedup_by_time: true,
              segment_count: 1,
              crop_applied: true,
              crop_start: "2023-04-19T23:55:00Z",
              crop_end: "2023-04-20T00:00:00Z",
              final_sample_count: 4
            },
            overall_statistics: {
              sampling: { cadence_median_seconds: 1, gap_count: 0, large_gap_threshold_seconds: 5 },
              magnetic: {
                status: "ok",
                product_type: "HPM_5",
                variables: {
                  B_abs: { status: "ok", finite_count: 4, min: 2.236, max: 17.378, mean: 9.801, median: 9.798, std: 5.64, unit: "nT" }
                }
              },
              position: {
                status: "ok",
                variables: {
                  GEO_LAT: { status: "ok", min: -5, max: 5, mean: 0, median: 0, std: 3.7, q25: -2.5, q75: 2.5, finite_count: 4, unit: "deg" },
                  GEO_LON: { status: "ok", min: 100, max: 110, mean: 105, median: 105, std: 3.7, q25: 102.5, q75: 107.5, finite_count: 4, unit: "deg" },
                  ALTITUDE: { status: "ok", min: 500, max: 505, mean: 502.5, median: 502.5, std: 1.8, q25: 501.25, q75: 503.75, finite_count: 4, unit: "km" }
                }
              },
              quality_flags: { "/FLAG_MT": { status: "ok", value_counts: { "0": 2, "1": 2 }, total_count: 4 } }
            },
            quality_flag_statistics: { "/FLAG_MT": { status: "ok", value_counts: { "0": 2, "1": 2 }, total_count: 4 } },
            per_file_statistics: [],
            per_segment_statistics: [],
            warnings: [],
            errors: [],
            generated_at: "2026-06-09T00:00:00Z",
            run_log_entry: "统计分析完成: session single-session，裁剪=是，最终样本 4，segments 1，重复时间样本去除 0，产品状态 single，输出 /tmp/statistics.json",
            artifacts: {
              statistics_json: { artifact_id: "stats-json", media_type: "application/json", path: "/tmp/statistics.json" },
              statistics_summary_csv: { artifact_id: "stats-csv", media_type: "text/csv", path: "/tmp/statistics_summary.csv" }
            }
          });
        }
        if (url.includes("/export")) {
          return jsonResponse({
            upload_session_id: "single-session",
            format: "csv",
            status: "ok",
            row_count: 4,
            artifact: { artifact_id: "export-csv", media_type: "text/csv" },
            manifest_artifact: { artifact_id: "manifest-json", media_type: "application/json" }
          });
        }
        return jsonResponse({});
      })
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders upload-only CSES HPM console", () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "CSES HPM 数据分析" })).toBeInTheDocument();
    expect(screen.getByText("图预览")).toBeInTheDocument();
    expect(screen.queryByText("DATE ARCHIVE")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "频谱图" })).toBeDisabled();
    expect(screen.getAllByRole("button", { name: "start!" }).length).toBeGreaterThan(0);
    expect(screen.queryByText("生成图像后可导出图片")).not.toBeInTheDocument();
  });

  it("uploads one file and switches to SINGLE FILE mode", async () => {
    render(<App />);
    const input = screen.getByLabelText("上传文件");
    const file = new File(["fake"], "one.h5", { type: "application/x-hdf5" });

    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => expect(screen.getAllByText("SINGLE FILE").length).toBeGreaterThan(0));
    expect(screen.getAllByText("demo_upload_1.h5").length).toBeGreaterThan(0);
    expect(screen.getAllByText("2023-04-20 07:55").length).toBeGreaterThan(0);
    expect(screen.getAllByText("2023-04-20 07:55 北京时间").length).toBeGreaterThan(0);
    expect(screen.getByLabelText("开始年")).toBeInTheDocument();
    expect(screen.getByLabelText("开始月")).toBeInTheDocument();
    expect(screen.getByLabelText("开始日")).toBeInTheDocument();
    expect(screen.getByLabelText("开始时")).toBeInTheDocument();
    expect(screen.getByLabelText("开始分")).toBeInTheDocument();
    const cropRows = document.querySelectorAll(".crop-selectors > .crop-selector");
    expect(cropRows).toHaveLength(2);
    expect(cropRows[0]).toHaveAttribute("aria-label", "开始时间");
    expect(cropRows[1]).toHaveAttribute("aria-label", "结束时间");
    expect(document.querySelector(".crop-label-cell > small")).toHaveTextContent("裁剪范围为可用时间段按北京时间选择");
    expect(document.querySelector(".crop-box > small")).not.toBeInTheDocument();
    expect(screen.getByText("按当前裁剪后的数据范围导出")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "export" })).toBeInTheDocument();
  });

  it("submits Beijing crop selection converted back to UTC for backend plotting", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<App />);
    const input = screen.getByLabelText("上传文件");
    const file = new File(["fake"], "one.h5", { type: "application/x-hdf5" });

    fireEvent.change(input, { target: { files: [file] } });
    await waitFor(() => expect(screen.getAllByText("SINGLE FILE").length).toBeGreaterThan(0));
    fireEvent.click(screen.getAllByRole("button", { name: "start!" })[0]);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/plot"), expect.anything()));
    const plotCall = fetchMock.mock.calls.find(([url]) => String(url).includes("/plot"));
    expect(plotCall).toBeTruthy();
    const body = JSON.parse(String(plotCall?.[1]?.body));
    expect(body.crop_range).toEqual({
      start: "2023-04-19T23:55:00Z",
      end: "2023-04-20T00:00:00Z"
    });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/statistics"), expect.anything()));
    const statsCall = fetchMock.mock.calls.find(([url]) => String(url).includes("/statistics"));
    const statsBody = JSON.parse(String(statsCall?.[1]?.body));
    expect(statsBody.crop_range).toEqual({
      start: "2023-04-19T23:55:00Z",
      end: "2023-04-20T00:00:00Z"
    });
  });

  it("shows feature statistics and downloads exported data/current plot", async () => {
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    render(<App />);
    const input = screen.getByLabelText("上传文件");
    const file = new File(["fake"], "one.h5", { type: "application/x-hdf5" });

    fireEvent.change(input, { target: { files: [file] } });
    await waitFor(() => expect(screen.getAllByText("SINGLE FILE").length).toBeGreaterThan(0));
    fireEvent.click(screen.getAllByRole("button", { name: "start!" })[0]);
    await waitFor(() => expect(screen.getByRole("img", { name: "plot" })).toBeInTheDocument());
    expect(screen.getByText("统计分析")).toBeInTheDocument();
    expect(screen.getByText("B_abs")).toBeInTheDocument();
    expect(screen.getByText("数据类型")).toBeInTheDocument();
    expect(screen.getByText("HPM5")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "位置范围统计表" })).toBeInTheDocument();
    expect(screen.getAllByText("始：").length).toBeGreaterThan(0);
    expect(screen.getAllByText("终：").length).toBeGreaterThan(0);
    expect(screen.getByText("-5deg")).toBeInTheDocument();
    expect(screen.getByText("5deg")).toBeInTheDocument();
    expect(screen.queryByText("-5 deg 至 5 deg")).not.toBeInTheDocument();
    expect(screen.getByRole("table", { name: "质量标志统计表" })).toBeInTheDocument();
    expect(screen.getAllByText("/FLAG_MT").length).toBeGreaterThan(0);
    expect(screen.getAllByText("未标记=2").length).toBeGreaterThan(0);
    expect(screen.getAllByText("磁力矩器干扰标记=2").length).toBeGreaterThan(0);
    expect(screen.queryByText("未标记=2, 磁力矩器干扰标记=2")).not.toBeInTheDocument();
    expect(screen.queryByText("/FLAG_MT: 0=2, 1=2")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "导出统计 JSON" })).toHaveAttribute("href", "/api/artifacts/stats-json?download=1");
    expect(screen.getByRole("link", { name: "导出统计 CSV" })).toHaveAttribute("href", "/api/artifacts/stats-csv?download=1");
    const plotDownload = screen.getByRole("link", { name: "导出当前图像" });
    expect(plotDownload).toHaveAttribute("href", "/api/artifacts/magnetic-png?download=1");
    expect(plotDownload).toHaveAttribute("download");

    fireEvent.click(screen.getByRole("button", { name: "export" }));

    await waitFor(() => expect(clickSpy).toHaveBeenCalled());
    clickSpy.mockRestore();
  });

  it("uploads two files and switches to BATCH mode with dedupe log", async () => {
    render(<App />);
    const input = screen.getByLabelText("上传文件");
    const files = [
      new File(["fake-a"], "a.h5", { type: "application/x-hdf5" }),
      new File(["fake-b"], "b.h5", { type: "application/x-hdf5" })
    ];

    fireEvent.change(input, { target: { files } });

    await waitFor(() => expect(screen.getAllByText("BATCH").length).toBeGreaterThan(0));
    expect(screen.getByText("重复文件去除: 1 个")).toBeInTheDocument();
    expect(screen.getByText("group_1")).toBeInTheDocument();
    expect(screen.getByText("2 个连续时间段 · 1 个绘图组")).toBeInTheDocument();
    expect(screen.getByText("去重后 4 个样本 · 北京时间")).toBeInTheDocument();
  });
});

describe("App static public demo workflow", () => {
  const originalDemoFlag = import.meta.env.VITE_DEMO_STATIC;

  beforeEach(() => {
    import.meta.env.VITE_DEMO_STATIC = "true";
    vi.resetModules();
  });

  afterEach(() => {
    import.meta.env.VITE_DEMO_STATIC = originalDemoFlag;
    vi.unstubAllGlobals();
  });

  it("loads static demo files without calling backend APIs", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("demo_summary.json")) {
        return jsonResponse({
          static_demo: true,
          mode: "github_pages_static",
          notice: "demo",
          session: staticUploadPayload(),
          plots: {
            magnetic: { artifact_id: "static-magnetic-overview", media_type: "image/png", label: "demo magnetic", url: "demo_data/magnetic_overview.png", download_url: "demo_data/magnetic_overview.png" },
            orbit: { artifact_id: "static-orbit-demo", media_type: "text/html", label: "demo orbit", url: "demo_data/orbit_demo.html", download_url: "demo_data/orbit_demo.html" }
          },
          downloads: {
            statistics_json: { artifact_id: "static-demo-statistics-json", media_type: "application/json", url: "demo_data/demo_statistics.json", download_url: "demo_data/demo_statistics.json" },
            statistics_summary_csv: { artifact_id: "static-demo-statistics-summary-csv", media_type: "text/csv", url: "demo_data/demo_statistics_summary.csv", download_url: "demo_data/demo_statistics_summary.csv" },
            manifest_json: { artifact_id: "static-demo-manifest-json", media_type: "application/json", url: "demo_data/demo_manifest.json", download_url: "demo_data/demo_manifest.json" }
          }
        });
      }
      if (url.endsWith("demo_statistics.json")) {
        return jsonResponse(staticStatisticsPayload());
      }
      return jsonResponse({});
    });
    vi.stubGlobal("fetch", fetchMock);
    const { default: StaticApp } = await import("./App");

    render(<StaticApp />);

    await waitFor(() => expect(screen.getByText("DEMO")).toBeInTheDocument());
    expect(screen.getAllByText("2000-12-17 07:55").length).toBeGreaterThan(0);
    expect(document.body).not.toHaveTextContent("2023-04-20");
    expect(screen.getByRole("img", { name: "demo magnetic" })).toHaveAttribute("src", expect.stringContaining("demo_data/magnetic_overview.png"));
    expect(screen.getByText("当前为 demo，不提供运行日志服务")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "频谱图" })).toHaveAttribute("title", "涉及其他数据，demo 版本不支持展示");
    expect(document.querySelector(".crop-label-cell")).toHaveAttribute("title", "demo 版本不支持裁剪功能");
    expect(document.querySelector(".crop-export-row")).toHaveAttribute("title", "sorry！下载达咩哦");
    const staticExportButton = screen.getByRole("button", { name: "export" });
    expect(staticExportButton).toBeDisabled();
    expect(staticExportButton).toHaveAttribute("title", "sorry！下载达咩哦");
    const staticExportSelect = document.querySelector(".crop-export-row select") as HTMLSelectElement;
    expect(staticExportSelect).not.toBeDisabled();
    expect(Array.from(staticExportSelect.options).map((option) => option.value)).toEqual(["csv", "dat", "h5"]);
    expect(screen.queryByRole("link", { name: "导出统计 JSON" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "导出统计 CSV" })).not.toBeInTheDocument();
    expect(screen.getByText("导出统计 JSON")).toHaveAttribute("title", "sorry！下载达咩哦");
    expect(screen.getByText("导出统计 CSV")).toHaveAttribute("title", "sorry！下载达咩哦");
    expect(screen.queryByRole("link", { name: "导出当前图像" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "上传文件" }));
    expect(screen.getByRole("alert")).toHaveTextContent("当前为 demo，脱敏数据已准备，不支持上传");
    expect(fetchMock.mock.calls.every(([url]) => !String(url).startsWith("/api"))).toBe(true);
  });
});

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" }
  });
}

function staticStatisticsPayload() {
  return {
    session_id: "static-public-demo",
    product_type_status: { status: "single", products: ["HPM_5"], product_type: "HPM_5" },
    time_range: {
      start_time: "2000-12-17T23:55:00Z",
      end_time: "2000-12-17T04:27:00Z",
      display_start_time: "2000-12-17 07:55",
      display_end_time: "2000-12-17 12:27"
    },
    processing_summary: {
      uploaded_file_count: 6,
      unique_file_count: 6,
      duplicate_file_count: 0,
      raw_sample_count: 300,
      merged_sample_count: 300,
      duplicate_time_removed_count: 0,
      sorted_by_time: true,
      dedup_by_time: true,
      segment_count: 6,
      crop_applied: false,
      crop_start: null,
      crop_end: null,
      final_sample_count: 300
    },
    overall_statistics: {
      sampling: { cadence_median_seconds: 1, gap_count: 5, large_gap_threshold_seconds: 5 },
      magnetic: {
        status: "ok",
        product_type: "HPM_5",
        variables: {
          B_abs: { status: "ok", finite_count: 300, min: 20000, max: 50000, mean: 33000, median: 32000, std: 7000, unit: "nT" }
        }
      },
      position: {
        status: "ok",
        variables: {
          GEO_LAT: { status: "ok", min: -67, max: 69, mean: 0, median: 0, std: 30, q25: -20, q75: 20, finite_count: 300, unit: "deg" },
          GEO_LON: { status: "ok", min: -180, max: 180, mean: 0, median: 0, std: 100, q25: -90, q75: 90, finite_count: 300, unit: "deg" },
          ALTITUDE: { status: "ok", min: 499, max: 519, mean: 509, median: 509, std: 5, q25: 503, q75: 515, finite_count: 300, unit: "km" }
        }
      },
      quality_flags: { "/FLAG_MT": { status: "ok", value_counts: { "0": 280, "1": 20 }, total_count: 300 } }
    },
    quality_flag_statistics: { "/FLAG_MT": { status: "ok", value_counts: { "0": 280, "1": 20 }, total_count: 300 } },
    per_file_statistics: [],
    per_segment_statistics: [],
    warnings: [],
    errors: [],
    generated_at: "2026-06-09T00:00:00Z",
    artifacts: {
      statistics_json: { artifact_id: "static-demo-statistics-json", media_type: "application/json", url: "demo_data/demo_statistics.json", download_url: "demo_data/demo_statistics.json" },
      statistics_summary_csv: { artifact_id: "static-demo-statistics-summary-csv", media_type: "text/csv", url: "demo_data/demo_statistics_summary.csv", download_url: "demo_data/demo_statistics_summary.csv" }
    }
  };
}
