import { describe, expect, it } from "vitest";

import {
  artifactUrl,
  capabilityRows,
  fileDisplayName,
  kindLabel,
  previewTable,
  productAvailability,
  unitLabel
} from "./format";

describe("frontend format helpers", () => {
  it("labels scientific variable kinds with compact user-facing text", () => {
    expect(kindLabel("magnetic_vector")).toBe("磁场矢量");
    expect(kindLabel("quality_flag")).toBe("质量标志");
    expect(kindLabel("be_ratio")).toBe("B/E ratio");
    expect(kindLabel("unknown_kind")).toBe("unknown_kind");
  });

  it("builds artifact URLs without exposing local file paths", () => {
    expect(artifactUrl("cluster:quicklook_B:20051203")).toBe("/api/artifacts/cluster%3Aquicklook_B%3A20051203");
  });

  it("summarizes Cluster product availability from product flags", () => {
    const availability = productAvailability({
      daily_full: { exists: true, size_bytes: 100 },
      quicklook_B: { exists: false, size_bytes: 0 },
      quicklook_E: { exists: true, size_bytes: 200 }
    });

    expect(availability).toEqual({
      total: 3,
      available: 2,
      missing: ["quicklook_B"]
    });
  });

  it("uses dates or file basenames for selector labels", () => {
    expect(fileDisplayName({ file_id: "20051203", date: "20051203" })).toBe("2005-12-03");
    expect(fileDisplayName({ file_id: "nested/CSES_01_HPM_5_L02_A2_sample.h5" })).toBe("CSES_01_HPM_5_L02_A2_sample.h5");
  });

  it("renders confirmed unit metadata objects as their value", () => {
    expect(unitLabel({ value: "nT", confidence: "confirmed" })).toBe("nT");
    expect(unitLabel("mV/m")).toBe("mV/m");
  });

  it("transposes a CSES subset response into preview table rows", () => {
    const rows = previewTable({
      variables: [
        { path: "/UTC_TIME", data: [[2023042001], [2023042002]] },
        { path: "/B_FGM", data: [[1, 2, 3], [4, 5, 6]] }
      ]
    });

    expect(rows.columns).toEqual(["样本", "/UTC_TIME", "/B_FGM"]);
    expect(rows.rows).toEqual([
      { 样本: 0, "/UTC_TIME": "2023042001", "/B_FGM": "1, 2, 3" },
      { 样本: 1, "/UTC_TIME": "2023042002", "/B_FGM": "4, 5, 6" }
    ]);
  });

  it("keeps capability flags explicit for disabled UI states", () => {
    expect(capabilityRows({ subset: true, plot_existing: false, plot_generate: true, stats: false })).toEqual([
      { key: "subset", label: "子集预览", enabled: true },
      { key: "plot_existing", label: "参考 quicklook", enabled: false },
      { key: "plot_generate", label: "生成图", enabled: true },
      { key: "stats", label: "统计", enabled: false }
    ]);
  });
});
