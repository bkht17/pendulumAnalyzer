import { useCallback } from "react";
import { Link, useParams } from "react-router";

import { useTrialMutations } from "../api/hooks";
import type { TrialInput } from "../api/types";
import { Stopwatch } from "../components/Stopwatch";
import { Empty, ErrorNotice } from "../components/Status";
import { TrialsTable } from "../components/TrialsTable";
import { VideosCard } from "../components/VideosCard";
import { DASH, ms, num, pm } from "../lib/format";
import { useExperimentContext } from "./experimentContext";

export function SeriesPage() {
  const { experiment } = useExperimentContext();
  const seriesId = Number(useParams().seriesId);
  const series = experiment.series.find((s) => s.id === seriesId);
  const trials = useTrialMutations(experiment.id);

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
          <h3>Участки видео при этой длине</h3>
          <span className="muted small">{series.segments.length}</span>
        </div>
        {series.segments.length === 0 ? (
          <p className="secondary small" style={{ margin: 0 }}>
            Пока ни один участок видео не привязан к этой длине. Загрузите видео ниже (если в нём одна серия, она
            привяжется сама) или привяжите участок на странице видео.
          </p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Видео</th>
                  <th>Время, с</th>
                  <th>T средний, с</th>
                  <th>T₀ (малые колеб.), с</th>
                  <th>Ошибка момента</th>
                  <th>Амплитуда</th>
                </tr>
              </thead>
              <tbody>
                {series.segments.map((seg) => (
                  <tr key={seg.id} className={seg.excluded ? "excluded" : undefined}>
                    <td>
                      <Link to={`${base}/videos/${seg.video_id}`}>{seg.video_name}</Link>
                    </td>
                    <td>
                      {num(seg.t_start, 1)}–{num(seg.t_end, 1)}
                    </td>
                    <td>{seg.result ? pm(seg.result.period, seg.result.period_se, 5) : DASH}</td>
                    <td>{seg.result?.t0 ? pm(seg.result.t0, seg.result.t0_se, 5) : DASH}</td>
                    <td>{ms(seg.result?.event_sigma)}</td>
                    <td>
                      {seg.result?.theta_max_deg != null
                        ? `${num(seg.result.theta_max_deg, 0)}° → ${num(seg.result.theta_min_deg, 0)}°`
                        : DASH}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <VideosCard experiment={experiment} seriesId={series.id} />
    </div>
  );
}
