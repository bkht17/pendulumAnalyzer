import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router";

import { api } from "../api/client";
import { keys, useTrack, useVideo, useVideoMutations } from "../api/hooks";
import type { ColorRange, Point, Segment, TrackingParams, Video } from "../api/types";
import { AmplitudeChart } from "../charts/AmplitudeChart";
import { PeriodsChart } from "../charts/PeriodsChart";
import { TrackChart } from "../charts/TrackChart";
import { ColorControls } from "../components/ColorControls";
import { FrameEditor, type Tool } from "../components/FrameEditor";
import { Kpi } from "../components/Kpi";
import { SegmentsPanel } from "../components/SegmentsPanel";
import { ErrorNotice, Loading } from "../components/Status";
import { VideoStatusBadge } from "../components/VideoStatusBadge";
import { DASH, ms, num, pct, pm } from "../lib/format";
import { useExperimentContext } from "./experimentContext";

type Settings = Omit<TrackingParams, "color" | "scale">;

const DEFAULT_SETTINGS: Settings = {
  method: "motion",
  roi: null,
  min_area: 30,
  motion_threshold: 25,
  polarity: "auto",
  t_start: null,
  t_end: null,
  axis: "auto",
  pivot: null,
};

const TOOLS: { id: Tool; label: string; hint: string; colorOnly?: boolean }[] = [
  { id: "roi", label: "Область поиска", hint: "Обведите рамкой зону, где качается груз (без лишних движущихся предметов)" },
  { id: "color", label: "Цвет маркера", hint: "Кликните по цветному маркеру на грузе", colorOnly: true },
  {
    id: "pivot",
    label: "Точка подвеса",
    hint: "Необязательно: подвес находится сам по дуге траектории. Отметьте, если амплитуда маленькая",
  },
  { id: "scale", label: "Масштаб", hint: "Кликните по двум точкам линейки и введите расстояние — получите длину нити по видео" },
];

function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return debounced;
}

const parseNum = (v: string) => (v ? Number(v.replace(",", ".")) : null);

export function VideoPage() {
  const videoId = Number(useParams().videoId);
  const query = useVideo(videoId);
  if (query.isPending) return <Loading />;
  if (query.isError) return <ErrorNotice error={query.error} />;
  return <VideoWorkspace key={query.data.id} video={query.data} />;
}

function VideoWorkspace({ video }: { video: Video }) {
  const { experiment } = useExperimentContext();
  const client = useQueryClient();
  const base = `/experiments/${experiment.id}`;
  const mutations = useVideoMutations(experiment.id);

  const [color, setColor] = useState<ColorRange | null>(video.params?.color ?? null);
  const [settings, setSettings] = useState<Settings>(() => {
    const stored: Partial<TrackingParams> = { ...video.params };
    delete stored.color;
    delete stored.scale;
    return { ...DEFAULT_SETTINGS, ...stored };
  });
  const [time, setTime] = useState(() => Math.min(video.params?.t_start ?? 0.5, video.duration_s / 2));
  const [tool, setTool] = useState<Tool>(video.params?.method === "color" && !video.params.color ? "color" : "roi");
  const [scalePoints, setScalePoints] = useState<Point[]>(() =>
    video.params?.scale ? [video.params.scale.p1, video.params.scale.p2] : [],
  );
  const [scaleCm, setScaleCm] = useState(() => String(video.params?.scale?.distance_cm ?? ""));
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const frameStep = 1 / (video.timing?.fps_measured || video.fps_nominal || 30);
  const busy = video.status === "queued" || video.status === "processing";
  const isColor = settings.method === "color";
  const set = <K extends keyof Settings>(key: K, value: Settings[K]) => setSettings((s) => ({ ...s, [key]: value }));

  // Когда обработка завершилась — обновить сводку эксперимента и анализ.
  const previousStatus = useRef(video.status);
  useEffect(() => {
    if (previousStatus.current !== video.status && (video.status === "done" || video.status === "failed")) {
      void client.invalidateQueries({ queryKey: keys.experiment(experiment.id) });
      void client.invalidateQueries({ queryKey: keys.analysis(experiment.id) });
    }
    previousStatus.current = video.status;
  }, [video.status, client, experiment.id]);

  const scale = useMemo(() => {
    const distance = parseNum(scaleCm);
    if (scalePoints.length !== 2 || !distance || !(distance > 0)) return null;
    return { p1: scalePoints[0]!, p2: scalePoints[1]!, distance_cm: distance };
  }, [scalePoints, scaleCm]);

  const fullParams: TrackingParams | null = useMemo(
    () => (isColor && !color ? null : { ...settings, color: isColor ? color : null, scale }),
    [settings, color, scale, isColor],
  );

  const previewInput = useDebounced(fullParams ? { time_s: time, params: fullParams } : null, 250);
  const preview = useQuery({
    queryKey: ["preview", video.id, previewInput],
    queryFn: () => api.preview(video.id, previewInput!),
    enabled: previewInput !== null,
    placeholderData: keepPreviousData,
    staleTime: Infinity,
    retry: false,
  });

  const sample = useMutation({
    mutationFn: (p: Point) => api.sampleColor(video.id, { time_s: time, x: Math.round(p.x), y: Math.round(p.y) }),
    onSuccess: (c) => {
      setColor(c);
      setTool("roi");
    },
  });

  const track = useTrack(video);
  const selected: Segment | null = video.segments.find((s) => s.id === selectedId) ?? null;
  const axis = video.track_info?.axis ?? "x";

  const onPoint = (p: Point) => {
    if (tool === "color") sample.mutate(p);
    else if (tool === "pivot") set("pivot", p);
    else if (tool === "scale") setScalePoints((pts) => (pts.length >= 2 ? [p] : [...pts, p]));
  };

  const run = () => {
    setSelectedId(null);
    if (fullParams) mutations.track.mutate({ id: video.id, params: fullParams });
  };

  const sameJson = (a: unknown, b: unknown) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
  const geometryChanged =
    !!video.params && (!sameJson(video.params.pivot, settings.pivot) || !sameJson(video.params.scale, scale));
  const timing = video.timing;
  const previewData = previewInput ? preview.data : undefined;
  const tools = TOOLS.filter((t) => !t.colorOnly || isColor);
  const assigned = video.segments.filter((s) => s.series_id && !s.excluded).length;

  return (
    <div className="stack">
      <div className="breadcrumbs">
        <Link to={base}>Измерения</Link> / {video.original_name}
      </div>
      <div className="row">
        <h2 style={{ margin: 0 }}>{video.original_name}</h2>
        <VideoStatusBadge video={video} />
        <span className="muted small">
          {video.width}×{video.height} · {num(video.fps_nominal, 2)} кадр/с · {num(video.duration_s, 1)} с ·{" "}
          {video.frame_count} кадров
        </span>
      </div>

      <div className="video-layout">
        <section className="card stack">
          <div className="segmented" role="tablist">
            {tools.map((t) => (
              <button key={t.id} className={tool === t.id ? "active" : ""} onClick={() => setTool(t.id)}>
                {t.label}
              </button>
            ))}
          </div>
          <div className="small secondary">{tools.find((t) => t.id === tool)?.hint}</div>
          <FrameEditor
            src={api.frameUrl(video.id, time)}
            videoWidth={video.width}
            videoHeight={video.height}
            tool={tool}
            roi={settings.roi}
            pivot={settings.pivot ?? selected?.result?.pivot_px ?? null}
            scalePoints={scalePoints}
            detection={previewData?.found ? { x: previewData.x!, y: previewData.y! } : null}
            mask={previewData ? { png: previewData.mask_png, roi: previewData.roi } : null}
            onPoint={onPoint}
            onRoi={(roi) => set("roi", roi)}
          />
          <div className="row">
            <button className="small" onClick={() => setTime((t) => Math.max(t - 1, 0))}>
              −1 с
            </button>
            <button className="small" onClick={() => setTime((t) => Math.max(t - frameStep, 0))}>
              −кадр
            </button>
            <input
              type="range"
              min={0}
              max={Math.max(video.duration_s - frameStep, 0)}
              step={frameStep}
              value={time}
              onChange={(e) => setTime(Number(e.target.value))}
              style={{ flex: 1, minWidth: 120 }}
              aria-label="Время кадра"
            />
            <button className="small" onClick={() => setTime((t) => Math.min(t + frameStep, video.duration_s))}>
              +кадр
            </button>
            <button className="small" onClick={() => setTime((t) => Math.min(t + 1, video.duration_s))}>
              +1 с
            </button>
            <span className="nums small">{num(time, 3)} с</span>
          </div>
          {sample.isError && <ErrorNotice error={sample.error} />}
          {preview.isError && previewInput && <ErrorNotice error={preview.error} />}
          {preview.isFetching && !previewData && <div className="muted small">Строю фон для предпросмотра…</div>}
          {previewData && (
            <div className={`notice ${previewData.found ? "notice--good" : "notice--warn"}`}>
              {previewData.found
                ? `✓ Груз найден на этом кадре: (${num(previewData.x, 1)}; ${num(previewData.y, 1)}), площадь пятна ${previewData.area} px. Проверьте несколько кадров слайдером.`
                : isColor
                  ? "! На этом кадре маркер не найден — расширьте диапазон цвета или проверьте область поиска."
                  : "! На этом кадре груз не найден — возможно, он сейчас неподвижен (держат рукой) или порог отличия от фона слишком высок."}
            </div>
          )}
        </section>

        <aside className="stack">
          <section className="card stack">
            <h3>Как искать груз</h3>
            <div className="segmented">
              <button className={!isColor ? "active" : ""} onClick={() => set("method", "motion")}>
                Движение (без маркера)
              </button>
              <button
                className={isColor ? "active" : ""}
                onClick={() => {
                  set("method", "color");
                  if (!color) setTool("color");
                }}
              >
                Цвет маркера
              </button>
            </div>
            {isColor ? (
              color ? (
                <ColorControls color={color} onChange={setColor} />
              ) : (
                <p className="secondary small">Выберите инструмент «Цвет маркера» и кликните по маркеру на кадре.</p>
              )
            ) : (
              <>
                <p className="secondary small" style={{ margin: 0 }}>
                  Фон — медиана кадров, груз — то, что от него отличается. Подходит для любого груза, в том
                  числе стального шарика без маркера.
                </p>
                <label className="field">
                  Порог отличия от фона: {settings.motion_threshold}
                  <input
                    type="range"
                    min={8}
                    max={80}
                    value={settings.motion_threshold}
                    onChange={(e) => set("motion_threshold", Number(e.target.value))}
                  />
                </label>
                <label className="field">
                  Груз относительно фона
                  <select value={settings.polarity} onChange={(e) => set("polarity", e.target.value as Settings["polarity"])}>
                    <option value="auto">Определить автоматически</option>
                    <option value="dark">Темнее фона</option>
                    <option value="bright">Светлее фона</option>
                  </select>
                </label>
              </>
            )}
            <label className="field">
              Минимальная площадь пятна, px
              <input
                type="number"
                min={1}
                value={settings.min_area}
                onChange={(e) => set("min_area", Math.max(1, Number(e.target.value)))}
              />
            </label>
          </section>

          <section className="card stack">
            <h3>Интервал и геометрия</h3>
            <div className="form-row">
              <label className="field">
                Начало, с
                <input
                  inputMode="decimal"
                  value={settings.t_start ?? ""}
                  placeholder="0"
                  onChange={(e) => set("t_start", parseNum(e.target.value))}
                />
              </label>
              <label className="field">
                Конец, с
                <input
                  inputMode="decimal"
                  value={settings.t_end ?? ""}
                  placeholder={num(video.duration_s, 1)}
                  onChange={(e) => set("t_end", parseNum(e.target.value))}
                />
              </label>
            </div>
            <p className="muted small" style={{ margin: 0 }}>
              Обычно не нужно: серии колебаний в длинной записи находятся автоматически.
            </p>
            <label className="field">
              Ось колебаний
              <select value={settings.axis} onChange={(e) => set("axis", e.target.value as Settings["axis"])}>
                <option value="auto">Автоматически</option>
                <option value="x">Горизонтальная (x)</option>
                <option value="y">Вертикальная (y)</option>
              </select>
            </label>
            <div className="small secondary">
              Область поиска: {settings.roi ? `${settings.roi.w}×${settings.roi.h} px` : "весь кадр"}{" "}
              {settings.roi && (
                <button className="small ghost" onClick={() => set("roi", null)}>
                  сбросить
                </button>
              )}
            </div>
            <div className="small secondary">
              Точка подвеса:{" "}
              {settings.pivot ? `(${num(settings.pivot.x, 0)}; ${num(settings.pivot.y, 0)})` : "найдётся по дуге"}{" "}
              {settings.pivot && (
                <button className="small ghost" onClick={() => set("pivot", null)}>
                  сбросить
                </button>
              )}
            </div>
            <label className="field">
              Масштаб: расстояние между точками, см
              <input
                inputMode="decimal"
                value={scaleCm}
                onChange={(e) => setScaleCm(e.target.value)}
                placeholder={scalePoints.length === 2 ? "например, 30" : "сначала отметьте 2 точки"}
              />
            </label>
            {scale && (
              <div className="small secondary">
                {num(Math.hypot(scale.p1.x - scale.p2.x, scale.p1.y - scale.p2.y) / scale.distance_cm, 2)} px/см
              </div>
            )}
          </section>

          <section className="card stack">
            <button className="primary" disabled={!fullParams || busy || mutations.track.isPending} onClick={run}>
              {video.status === "done" || video.status === "failed" ? "Обработать заново" : "Запустить трекинг"}
            </button>
            {busy && (
              <div className="stack">
                <div className="progress">
                  <div style={{ width: `${video.progress * 100}%` }} />
                </div>
                <div className="small secondary">
                  {video.status === "queued" ? "В очереди…" : `Обработка: ${num(video.progress * 100, 0)} %`}
                </div>
              </div>
            )}
            {geometryChanged && video.status === "done" && (
              <button
                disabled={mutations.geometry.isPending}
                onClick={() => mutations.geometry.mutate({ id: video.id, body: { pivot: settings.pivot, scale } })}
              >
                Применить подвес и масштаб (без повторного трекинга)
              </button>
            )}
            {video.status === "failed" && video.error && <div className="notice notice--critical">{video.error}</div>}
            {mutations.track.isError && <ErrorNotice error={mutations.track.error} />}
            {mutations.geometry.isError && <ErrorNotice error={mutations.geometry.error} />}
          </section>
        </aside>
      </div>

      {timing && (timing.variable_frame_rate || timing.dropped_frames > 0) && (
        <div className="notice notice--warn">
          ! Переменная частота кадров (разброс интервалов {pct(timing.frame_interval_jitter * 100, 1)}
          {timing.dropped_frames > 0 && `, пропусков: ${timing.dropped_frames}`}). Время каждого кадра взято из
          метки времени файла, поэтому на результат это не влияет, но для отчёта стоит отметить.
        </div>
      )}

      {video.track_info && (
        <section className="card stack">
          <div className="card__title">
            <h3>Найденные серии колебаний</h3>
            <span className="muted small">
              груз найден на {pct(video.track_info.detection_rate * 100, 1)} кадров · привязано к длинам: {assigned} из{" "}
              {video.segments.length}
            </span>
          </div>
          <p className="secondary small" style={{ margin: 0 }}>
            Каждая серия — отрезок свободных колебаний без рук. Привяжите её к длине нити: в анализ попадают только
            привязанные участки. T₀ — период, пересчитанный к малой амплитуде; его и стоит сравнивать с формулой.
          </p>
          <SegmentsPanel video={video} experiment={experiment} selectedId={selectedId} onSelect={setSelectedId} />
        </section>
      )}

      {track.data && (
        <section className="card">
          <div className="card__title">
            <h3>{selected ? `Движение груза: участок ${num(selected.t_start, 1)}–${num(selected.t_end, 1)} с` : "Движение груза"}</h3>
            <div className="row">
              {selected && (
                <button className="small" onClick={() => setSelectedId(null)}>
                  Вся запись
                </button>
              )}
              <a className="button small" href={api.trackCsvUrl(video.id)} download>
                Скачать CSV
              </a>
            </div>
          </div>
          <TrackChart track={track.data} axis={axis} segments={video.segments} selected={selected} onSelect={setSelectedId} />
        </section>
      )}

      {selected?.result && <SegmentDetails segment={selected} />}
    </div>
  );
}

function SegmentDetails({ segment }: { segment: Segment }) {
  const r = segment.result!;
  return (
    <>
      <div className="kpis">
        <Kpi label="Средний период T" value={`${pm(r.period, r.period_se, 5)} с`} hint="как измерил бы секундомер, но точнее" />
        <Kpi
          label="Период при малой амплитуде T₀"
          value={r.t0 ? `${pm(r.t0, r.t0_se, 5)} с` : DASH}
          hint={r.t0 ? "с учётом поправки θ²/16 для каждого периода" : "угол амплитуды не определён"}
        />
        <Kpi label="Ошибка фиксации момента" value={ms(r.event_sigma)} hint="у секундомера обычно 30–60 мс" />
        <Kpi
          label="Амплитуда"
          value={r.theta_max_deg != null ? `${num(r.theta_max_deg, 1)}° → ${num(r.theta_min_deg, 1)}°` : `${num(r.amplitude_start_px, 0)} px`}
          hint={r.damping != null ? `затухание γ = ${num(r.damping, 4)} 1/с` : undefined}
        />
        <Kpi
          label="Колебаний на участке"
          value={num(r.periods_observed, 1)}
          hint={`${r.period_values.length} отдельных периодов${r.outliers ? `, отброшено сбоев: ${r.outliers}` : ""}`}
        />
        {r.length_from_video_cm != null && (
          <Kpi label="Длина нити по видео" value={`${num(r.length_from_video_cm, 1)} см`} hint="по дуге траектории и масштабу" />
        )}
      </div>
      <div className="grid-2">
        <section className="card">
          <h3>Период от амплитуды</h3>
          <AmplitudeChart result={r} />
        </section>
        <section className="card">
          <h3>Отдельные периоды по времени</h3>
          <PeriodsChart result={r} />
        </section>
      </div>
    </>
  );
}
