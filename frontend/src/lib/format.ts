type ProductFlag = {
  exists?: boolean;
  size_bytes?: number;
};

type FileLike = {
  file_id?: string;
  date?: string;
  name?: string;
};

type SubsetVariable = {
  path: string;
  data: unknown;
};

type SubsetPayload = {
  variables?: SubsetVariable[];
};

type CapabilityMap = Record<string, boolean | undefined>;

const KIND_LABELS: Record<string, string> = {
  magnetic_vector: "磁场矢量",
  magnetic: "磁场",
  electric_vector: "电场矢量",
  electric: "电场",
  spectrogram: "频谱",
  context: "上下文",
  frequency_axis: "频率轴",
  be_ratio: "B/E ratio",
  quality_flag: "质量标志",
  time: "时间",
  dataset: "数据集"
};

const CAPABILITY_LABELS: Record<string, string> = {
  subset: "子集预览",
  plot_existing: "参考 quicklook",
  plot_generate: "生成图",
  stats: "统计",
  variables: "变量",
  metadata: "元数据"
};

export function kindLabel(kind: string | undefined): string {
  if (!kind) {
    return "数据集";
  }
  return KIND_LABELS[kind] ?? kind;
}

export function artifactUrl(artifactId: string): string {
  return `/api/artifacts/${encodeURIComponent(artifactId)}`;
}

export function productAvailability(products: Record<string, ProductFlag> | undefined) {
  const entries = Object.entries(products ?? {});
  const missing = entries.filter(([, value]) => !value.exists).map(([key]) => key);
  return {
    total: entries.length,
    available: entries.length - missing.length,
    missing
  };
}

export function fileDisplayName(file: FileLike): string {
  if (file.date && /^\d{8}$/.test(file.date)) {
    return `${file.date.slice(0, 4)}-${file.date.slice(4, 6)}-${file.date.slice(6, 8)}`;
  }
  const id = file.name || file.file_id || "";
  return id.split("/").filter(Boolean).at(-1) || id;
}

export function formatScalar(value: unknown): string {
  if (Array.isArray(value)) {
    return value.map((item) => formatScalar(item)).join(", ");
  }
  if (value === null || value === undefined) {
    return "";
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    return Number.isInteger(value) ? String(value) : value.toPrecision(6);
  }
  return String(value);
}

export function unitLabel(unit: unknown): string {
  if (unit === null || unit === undefined || unit === "") {
    return "";
  }
  if (typeof unit === "string" || typeof unit === "number" || typeof unit === "boolean") {
    return String(unit);
  }
  if (typeof unit === "object") {
    const payload = unit as { value?: unknown; label?: unknown; name?: unknown; text?: unknown };
    const value = payload.value ?? payload.label ?? payload.name ?? payload.text;
    if (value !== undefined && value !== null) {
      return formatScalar(value);
    }
    return JSON.stringify(unit);
  }
  return String(unit);
}

export function previewTable(payload: SubsetPayload) {
  const variables = payload.variables ?? [];
  const maxRows = variables.reduce((count, variable) => {
    return Math.max(count, Array.isArray(variable.data) ? variable.data.length : 0);
  }, 0);
  const columns = ["样本", ...variables.map((variable) => variable.path)];
  const rows = Array.from({ length: maxRows }, (_, index) => {
    const row: Record<string, string | number> = { 样本: index };
    for (const variable of variables) {
      const values = Array.isArray(variable.data) ? variable.data : [];
      row[variable.path] = formatScalar(values[index]);
    }
    return row;
  });
  return { columns, rows };
}

export function capabilityRows(capabilities: CapabilityMap) {
  return ["subset", "plot_existing", "plot_generate", "stats"].map((key) => ({
    key,
    label: CAPABILITY_LABELS[key],
    enabled: Boolean(capabilities[key])
  }));
}

export function bytesLabel(bytes: number | undefined): string {
  if (!bytes || bytes <= 0) {
    return "0 B";
  }
  const units = ["B", "KB", "MB", "GB"];
  let size = bytes;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size >= 10 || unit === 0 ? size.toFixed(0) : size.toFixed(1)} ${units[unit]}`;
}

export function numberLabel(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "-";
  }
  if (Math.abs(value) >= 1000 || (Math.abs(value) > 0 && Math.abs(value) < 0.001)) {
    return value.toExponential(4);
  }
  return value.toFixed(4);
}
