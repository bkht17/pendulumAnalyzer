import { useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { keys, useTrialMutations, useVideoMutations } from "../api/hooks";
import type { TrialInput } from "../api/types";
import { Stopwatch } from "../components/Stopwatch";
import { Empty, ErrorNotice } from "../components/Status";
import { TrialsTable } from "../components/TrialsTable";
import { VideoStatusBadge } from "../components/VideoStatusBadge";
import { VideoUpload } from "../components/VideoUpload";
import { bytes, DASH, ms, num, pm } from "../lib/format";
import { useExperimentContext } from "./experimentContext";

export function SeriesPage() {
  const { experiment } = useExperimentContext();
  const seriesId = Number(useParams().seriesId);
  const navigate = useNavigate();
  const series = experiment.series.find((s) => s.id === seriesId);
  const trials = useTrialMutations(experiment.id);
  const videos = useVideoMutations(experiment.id);
  const client = useQueryClient();

  const createTrial = trials.create.mutate;
  const addTrial = useCallback(
    (input: TrialInput) => createTrial({ seriesId, input }),
    [createTrial, seriesId],
  );

  if (!series) return <Empty>Такой длины нет в эксперименте.</Empty>;
  const base = `/experiments/${experiment.id}`;

  return (
    <div className="stack">
      <div className="breadcrumbs">
        <Link to={base}>Измерения</Link> / L = {num(series.length_cm, 1)} см
      </div>
      <h2>
        Длина L = {num(series.length_cm, 1)} ± {num(series.length_sigma_cm, 1)} см
        {series.amplitude_deg !== null && (
          <span className="secondary"> · угол ≈ {num(series.amplitude_deg, 0)}°</span>
        )}
      </h2>

      <div className="grid-2">
        <section className="card">
          <div className="card__title">
            <h3>Секундомер</h3>
          </div>
          <Stopwatch
            defaultPeriods={experiment.main_periods}
            saving={trials.create.isPending}
            onSave={(input) => addTrial({ ...input, source: "app" })}
          />
        </section>

        <section className="card">
          <div className="card__title">
            <h3>Ручные замеры</h3>
            <span className="muted small">{series.trials.length}</span>
          </div>
          <TrialsTable
            trials={series.trials}
            mainPeriods={experiment.main_periods}
            busy={trials.create.isPending}
            onAdd={addTrial}
            onToggle={(t) => trials.toggleExcluded.mutate({ id: t.id, excluded: !t.excluded })}
            onDelete={(t) => trials.remove.mutate(t.id)}
          />
          {trials.create.isError && <ErrorNotice error={trials.create.error} />}
        </section>
      </div>

      <section className="card stack">
        <div className="card__title">
          <h3>Видеозаписи</h3>
        </div>
        <VideoUpload
          seriesId={series.id}
          onUploaded={(video) => {
            void client.invalidateQueries({ queryKey: keys.experiment(experiment.id) });
            navigate(`${base}/videos/${video.id}`);
          }}
        />
        {series.videos.length > 0 && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Файл</th>
                  <th className="left">Статус</th>
                  <th>Кадров/с</th>
                  <th>Длительность</th>
                  <th>T, с</th>
                  <th>Ошибка момента</th>
                  <th>Амплитуда</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {series.videos.map((v) => (
                  <tr key={v.id} className={v.excluded ? "excluded" : undefined}>
                    <td>
                      <Link to={`${base}/videos/${v.id}`}>{v.original_name}</Link>
                      <div className="muted small">
                        {v.width}×{v.height} · {bytes(v.size_bytes)}
                      </div>
                    </td>
                    <td className="left">
                      <VideoStatusBadge video={v} />
                    </td>
                    <td>{num(v.timing?.fps_measured ?? v.fps_nominal, 2)}</td>
                    <td>{num(v.duration_s, 1)} с</td>
                    <td>{v.result ? pm(v.result.period, v.result.period_se) : DASH}</td>
                    <td>{ms(v.result?.event_sigma)}</td>
                    <td>
                      {v.result?.amplitude_mean_deg != null
                        ? `${num(v.result.amplitude_mean_deg, 1)}°`
                        : DASH}
                    </td>
                    <td className="actions">
                      <div className="row" style={{ gap: 4, flexWrap: "nowrap" }}>
                        <Link className="button small" to={`${base}/videos/${v.id}`}>
                          {v.status === "uploaded" ? "Настроить" : "Открыть"}
                        </Link>
                        <button
                          className="small ghost"
                          onClick={() => videos.toggleExcluded.mutate({ id: v.id, excluded: !v.excluded })}
                        >
                          {v.excluded ? "Вернуть" : "Исключить"}
                        </button>
                        <button
                          className="small ghost danger"
                          onClick={() => confirm(`Удалить ${v.original_name}?`) && videos.remove.mutate(v.id)}
                        >
                          Удалить
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
