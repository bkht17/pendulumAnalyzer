import type {
  Analysis,
  ColorRange,
  Experiment,
  ExperimentDetail,
  ExperimentInput,
  Preview,
  Series,
  SeriesInput,
  TrackData,
  TrackingParams,
  Trial,
  TrialInput,
  Video,
} from "./types";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function errorMessage(status: number, body: unknown): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    // FastAPI 422: список ошибок валидации
    if (Array.isArray(detail)) {
      return detail
        .map((d: { loc?: unknown[]; msg?: string }) =>
          [d.loc?.slice(1).join("."), d.msg].filter(Boolean).join(": "),
        )
        .join("; ");
    }
  }
  return `Ошибка сервера (${status})`;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status === 204) return undefined as T;
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, errorMessage(response.status, data));
  return data as T;
}

/** Загрузка через XHR — у fetch нет событий прогресса отправки. */
function uploadWithProgress<T>(
  path: string,
  file: File,
  onProgress: (fraction: number) => void,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api${path}`);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded / event.total);
    };
    xhr.onload = () => {
      let data: unknown = null;
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        /* пустой или не-JSON ответ */
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data as T);
      else reject(new ApiError(xhr.status, errorMessage(xhr.status, data)));
    };
    xhr.onerror = () => reject(new ApiError(0, "Нет связи с сервером"));
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}

export const api = {
  experiments: () => request<Experiment[]>("GET", "/experiments"),
  experiment: (id: number) => request<ExperimentDetail>("GET", `/experiments/${id}`),
  createExperiment: (input: ExperimentInput) => request<Experiment>("POST", "/experiments", input),
  createDemo: () => request<Experiment>("POST", "/experiments/demo"),
  updateExperiment: (id: number, patch: Partial<ExperimentInput>) =>
    request<Experiment>("PATCH", `/experiments/${id}`, patch),
  deleteExperiment: (id: number) => request<void>("DELETE", `/experiments/${id}`),
  analysis: (id: number) => request<Analysis>("GET", `/experiments/${id}/analysis`),
  exportUrl: (id: number) => `/api/experiments/${id}/export.csv`,

  createSeries: (experimentId: number, input: SeriesInput) =>
    request<Series>("POST", `/experiments/${experimentId}/series`, input),
  updateSeries: (id: number, patch: Partial<SeriesInput>) =>
    request<Series>("PATCH", `/series/${id}`, patch),
  deleteSeries: (id: number) => request<void>("DELETE", `/series/${id}`),

  createTrial: (seriesId: number, input: TrialInput) =>
    request<Trial>("POST", `/series/${seriesId}/trials`, input),
  updateTrial: (id: number, patch: { excluded?: boolean }) =>
    request<Trial>("PATCH", `/trials/${id}`, patch),
  deleteTrial: (id: number) => request<void>("DELETE", `/trials/${id}`),

  uploadVideo: (seriesId: number, file: File, onProgress: (f: number) => void) =>
    uploadWithProgress<Video>(`/series/${seriesId}/videos`, file, onProgress),
  video: (id: number) => request<Video>("GET", `/videos/${id}`),
  updateVideo: (id: number, patch: { excluded?: boolean }) =>
    request<Video>("PATCH", `/videos/${id}`, patch),
  deleteVideo: (id: number) => request<void>("DELETE", `/videos/${id}`),
  frameUrl: (id: number, t: number, maxWidth = 1280) =>
    `/api/videos/${id}/frame?t=${t.toFixed(3)}&max_width=${maxWidth}`,
  sampleColor: (id: number, body: { time_s: number; x: number; y: number; radius?: number }) =>
    request<ColorRange>("POST", `/videos/${id}/sample-color`, body),
  preview: (id: number, body: { time_s: number; params: TrackingParams }) =>
    request<Preview>("POST", `/videos/${id}/preview`, body),
  startTracking: (id: number, params: TrackingParams) =>
    request<Video>("POST", `/videos/${id}/track`, params),
  track: (id: number) => request<TrackData>("GET", `/videos/${id}/track`),
  trackCsvUrl: (id: number) => `/api/videos/${id}/track.csv`,
};
