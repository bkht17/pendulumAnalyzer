import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router";

import { api } from "../api/client";
import { keys, useTrack, useVideo, useVideoMutations } from "../api/hooks";
import type { Point, TrackingParams, Video } from "../api/types";
import { PeriodsChart } from "../charts/PeriodsChart";
import { TrackChart } from "../charts/TrackChart";
import { ColorControls } from "../components/ColorControls";
import { FrameEditor, type Tool } from "../components/FrameEditor";
import { Kpi } from "../components/Kpi";
import { ErrorNotice, Loading } from "../components/Status";
import { VideoStatusBadge } from "../components/VideoStatusBadge";
import { DASH, ms, num, pct, pm } from "../lib/format";
import { useExperimentContext } from "./experimentContext";

const DEFAULT_PARAMS: Omit<TrackingParams, "color"> = {
  roi: null,
  min_area: 12,
  t_start: null,
  t_end: null,
  axis: "auto",
  pivot: null,
  scale: null,
};

const TOOLS: { id: Tool; label: string; hint: string }[] = [
  { id: "color", label: "Цвет маркера", hint: "Кликните по цветному маркеру на грузе" },
  { id: "roi", label: "Область поиска", hint: "Обведите рамкой зону, где качается груз" },
  { id: "pivot", label: "Точка подвеса", hint: "Кликните по точке крепления нити — для угла амплитуды" },
  { id: "scale", label: "Масштаб", hint: "Кликните по двум точкам линейки и введите расстояние" },
];

function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return debounced;
}

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
  const series = experiment.series.find((s) => s.id === video.series_id);
  const base = `/experiments/${experiment.id}`;
  const mutations = useVideoMutations(experiment.id);

  const [color, setColor] = useState(video.params?.color ?? null);
  const [params, setParams] = useState<Omit<TrackingParams, "color">>(() => ({
    ...DEFAULT_PARAMS,
    ...video.params,
  }));
  const [time, setTime] = useState(() => Math.min(video.params?.t_start ?? 0.5, video.duration_s / 2));
  const [tool, setTool] = useState<Tool>(video.params?.color ? "roi" : "color");
  const [scalePoints, setScalePoints] = useState<Point[]>(() =>
    video.params?.scale ? [video.params.scale.p1, video.params.scale.p2] : [],
  );
  const [scaleCm, setScaleCm] = useState(() => String(video.params?.scale?.distance_cm ?? ""));

  const frameStep = 1 / (video.timing?.fps_measured || video.fps_nominal || 30);
  const busy = video.status === "queued" || video.status === "processing";

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
    const distance = Number(scaleCm.replace(",", "."));
    if (scalePoints.length !== 2 || !(distance > 0)) return null;
    return { p1: scalePoints[0]!, p2: scalePoints[1]!, distance_cm: distance };
  }, [scalePoints, scaleCm]);

  const fullParams: TrackingParams | null = useMemo(
    () => (color ? { ...params, color, scale } : null),
    [color, params, scale],
  );

  const previewInput = useDebounced(fullParams ? { time_s: time, params: fullParams } : null, 200);
  const preview = useQuery({
    queryKey: ["preview", video.id, previewInput],
    queryFn: () => api.preview(video.id, previewInput!),
    enabled: previewInput !== null,
    placeholderData: keepPreviousData,
    staleTime: Infinity,
  });

  const sample = useMutation({
    mutationFn: (p: Point) => api.sampleColor(video.id, { time_s: time, x: Math.round(p.x), y: Math.round(p.y) }),
    onSuccess: (c) => {
      setColor(c);
      setTool("roi");
    },
  });

  const track = useTrack(video);

  const onPoint = (p: Point) => {
    if (tool === "color") sample.mutate(p);
    else if (tool === "pivot") setParams((s) => ({ ...s, pivot: p }));
    else if (tool === "scale") setScalePoints((pts) => (pts.length >= 2 ? [p] : [...pts, p]));
  };

  const run = () => fullParams && mutations.track.mutate({ id: video.id, params: fullParams });

  const result = video.result;
  const timing = video.timing;
  const previewData = previewInput ? preview.data : undefined;

  return (
    <div className="stack">
      <div className="breadcrumbs">
        <Link to={base}>Измерения</Link> /{" "}
        {series && <Link to={`${base}/series/${series.id}`}>L = {num(series.length_cm, 1)} см</Link>} /{" "}
        {video.original_name}
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
            {TOOLS.map((t) => (
              <button key={t.id} className={tool === t.id ? "active" : ""} onClick={() => setTool(t.id)}>
                {t.label}
              </button>
            ))}
          </div>
          <div className="small secondary">{TOOLS.find((t) => t.id === tool)?.hint}</div>
          <FrameEditor
            src={api.frameUrl(video.id, time)}
            videoWidth={video.width}
            videoHeight={video.height}
            tool={tool}
            roi={params.roi}
            pivot={params.pivot}
            scalePoints={scalePoints}
            detection={previewData?.found ? { x: previewData.x!, y: previewData.y! } : null}
            mask={previewData ? { png: previewData.mask_png, roi: previewData.roi } : null}
            onPoint={onPoint}
            onRoi={(roi) => setParams((s) => ({ ...s, roi }))}
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
          {previewData && (
            <div className={`notice ${previewData.found ? "notice--good" : "notice--warn"}`}>
              {previewData.found
                ? `✓ Маркер найден на этом кадре: (${num(previewData.x, 1)}; ${num(previewData.y, 1)}), площадь ${previewData.area} px. Проверьте несколько кадров слайдером.`
                : "! На этом кадре маркер не найден — расширьте диапазон цвета, уменьшите «Насыщ. от» / «Яркость от» или проверьте область поиска."}
            </div>
          )}
        </section>

        <aside className="stack">
          <section className="card stack">
            <h3>Цвет маркера</h3>
            {color ? (
              <ColorControls color={color} onChange={setColor} />
            ) : (
              <p className="secondary small">Выберите инструмент «Цвет маркера» и кликните по маркеру на кадре.</p>
            )}
            <label className="field">
              Минимальная площадь пятна, px
              <input
                type="number"
                min={1}
                value={params.min_area}
                onChange={(e) => setParams((s) => ({ ...s, min_area: Math.max(1, Number(e.target.value)) }))}
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
                  value={params.t_start ?? ""}
                  placeholder="0"
                  onChange={(e) =>
                    setParams((s) => ({ ...s, t_start: e.target.value ? Number(e.target.value.replace(",", ".")) : null }))
                  }
                />
              </label>
              <label className="field">
                Конец, с
                <input
                  inputMode="decimal"
                  value={params.t_end ?? ""}
                  placeholder={num(video.duration_s, 1)}
                  onChange={(e) =>
                    setParams((s) => ({ ...s, t_end: e.target.value ? Number(e.target.value.replace(",", ".")) : null }))
                  }
                />
              </label>
            </div>
            <div className="row small">
              <button className="small" onClick={() => setParams((s) => ({ ...s, t_start: Number(time.toFixed(3)) }))}>
                Начало = текущий кадр
              </button>
              <button className="small" onClick={() => setParams((s) => ({ ...s, t_end: Number(time.toFixed(3)) }))}>
                Конец = текущий кадр
              </button>
            </div>
            <p className="muted small" style={{ margin: 0 }}>
              Обрежьте начало, где груз ещё держит рука.
            </p>
            <label className="field">
              Ось колебаний
              <select
                value={params.axis}
                onChange={(e) => setParams((s) => ({ ...s, axis: e.target.value as TrackingParams["axis"] }))}
              >
                <option value="auto">Автоматически</option>
                <option value="x">Горизонтальная (x)</option>
                <option value="y">Вертикальная (y)</option>
              </select>
            </label>
            <div className="small secondary">
              Область поиска: {params.roi ? `${params.roi.w}×${params.roi.h} px` : "весь кадр"}{" "}
              {params.roi && (
                <button className="small ghost" onClick={() => setParams((s) => ({ ...s, roi: null }))}>
                  сбросить
                </button>
              )}
            </div>
            <div className="small secondary">
              Точка подвеса:{" "}
              {params.pivot ? `(${num(params.pivot.x, 0)}; ${num(params.pivot.y, 0)})` : "не отмечена"}{" "}
              {params.pivot && (
                <button className="small ghost" onClick={() => setParams((s) => ({ ...s, pivot: null }))}>
                  сбросить
                </button>
              )}
            </div>
            <div className="form-row">
              <label className="field">
                Масштаб: расстояние между точками, см
                <input
                  inputMode="decimal"
                  value={scaleCm}
                  onChange={(e) => setScaleCm(e.target.value)}
                  placeholder={scalePoints.length === 2 ? "например, 10" : "сначала отметьте 2 точки"}
                />
              </label>
            </div>
            {scale && (
              <div className="small secondary">
                {num(
                  Math.hypot(scale.p1.x - scale.p2.x, scale.p1.y - scale.p2.y) / scale.distance_cm,
                  2,
                )}{" "}
                px/см
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
                  {video.status === "queued" ? "В очереди…" : `Обработка кадров: ${num(video.progress * 100, 0)} %`}
                </div>
              </div>
            )}
            {video.status === "failed" && video.error && <div className="notice notice--critical">{video.error}</div>}
            {mutations.track.isError && <ErrorNotice error={mutations.track.error} />}
          </section>
        </aside>
      </div>

      {timing && (timing.variable_frame_rate || timing.dropped_frames > 0) && (
        <div className="notice notice--warn">
          ! Переменная частота кадров (разброс интервалов {pct(timing.frame_interval_jitter * 100, 1)}
          {timing.dropped_frames > 0 && `, пропусков: ${timing.dropped_frames}`}). Время каждого кадра
          взято из метки времени файла, поэтому на результат это не влияет, но для отчёта стоит
          отметить.
        </div>
      )}

      {result && video.status === "done" && (
        <section className="stack">
          <div className="kpis">
            <Kpi label="Период T" value={`${pm(result.period, result.period_se)} с`} hint="регрессия моментов прохождения равновесия" />
            <Kpi label="Ошибка фиксации момента" value={ms(result.event_sigma)} hint="у секундомера обычно 30–60 мс" />
            <Kpi label="Разброс отдельных периодов" value={ms(result.period_std)} hint={`${result.period_values.length} периодов`} />
            <Kpi
              label="Амплитуда"
              value={
                result.amplitude_start_deg != null
                  ? `${num(result.amplitude_start_deg, 1)}° → ${num(result.amplitude_mean_deg, 1)}°`
                  : `${num(result.amplitude_start_px, 0)} px`
              }
              hint={result.amplitude_start_deg != null ? "начальная → средняя" : "отметьте точку подвеса, чтобы получить угол"}
            />
            <Kpi
              label="Маркер найден"
              value={pct(result.detection_rate * 100, 1)}
              hint={`${result.frames_analyzed} кадров, ${num(result.periods_observed, 1)} колебаний`}
            />
            <Kpi
              label="Подгонка синусоидой"
              value={result.fit ? `${num(result.fit.period, 5)} с` : DASH}
              hint={result.fit ? `затухание γ = ${num(result.fit.damping, 4)} 1/с` : "не сошлась"}
            />
            {result.length_from_video_cm != null && (
              <Kpi
                label="Длина по видео"
                value={`${num(result.length_from_video_cm, 1)} см`}
                hint={series ? `измерено линейкой: ${num(series.length_cm, 1)} см` : undefined}
              />
            )}
          </div>
          {result.amplitude_start_deg != null && result.amplitude_start_deg > 10 && (
            <div className="notice notice--warn">
              ! Амплитуда больше 10° — поправка к периоду превышает 0,2 %. Для чистого сравнения с
              формулой уменьшите угол отклонения до 5–7°.
            </div>
          )}
        </section>
      )}

      {track.data && (
        <section className="card">
          <div className="card__title">
            <h3>Движение маркера</h3>
            <a className="button small" href={api.trackCsvUrl(video.id)} download>
              Скачать CSV
            </a>
          </div>
          <TrackChart track={track.data} result={video.status === "done" ? result : null} />
        </section>
      )}

      {result && video.status === "done" && result.period_values.length > 1 && (
        <section className="card">
          <div className="card__title">
            <h3>Отдельные периоды</h3>
          </div>
          <PeriodsChart result={result} />
        </section>
      )}
    </div>
  );
}

