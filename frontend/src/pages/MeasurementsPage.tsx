import { type FormEvent, useState } from "react";
import { Link } from "react-router";

import { useSeriesMutations } from "../api/hooks";
import type { Series } from "../api/types";
import { ErrorNotice } from "../components/Status";
import { VideoStatusBadge } from "../components/VideoStatusBadge";
import { DASH, num } from "../lib/format";
import { useExperimentContext } from "./experimentContext";

const PRESET_LENGTHS = [20, 25, 40, 60, 80, 100];

function quickStats(series: Series, mainPeriods: number) {
  const trials = series.trials.filter((t) => !t.excluded && t.periods === mainPeriods);
  const swMean = trials.length ? trials.reduce((a, t) => a + t.period_s, 0) / trials.length : null;
  const done = series.videos.filter((v) => v.status === "done" && !v.excluded && v.result);
  const camMean = done.length
    ? done.reduce((a, v) => a + (v.result?.period ?? 0), 0) / done.length
    : null;
  return { trials: trials.length, swMean, camMean };
}

export function MeasurementsPage() {
  const { experiment } = useExperimentContext();
  const { create, remove } = useSeriesMutations(experiment.id);
  const [length, setLength] = useState("");
  const [sigma, setSigma] = useState("0.3");
  const [angle, setAngle] = useState("");

  const existing = new Set(experiment.series.map((s) => s.length_cm));
  const parse = (v: string) => Number(v.replace(",", "."));

  const submit = (event: FormEvent) => {
    event.preventDefault();
    create.mutate(
      {
        length_cm: parse(length),
        length_sigma_cm: parse(sigma),
        amplitude_deg: angle ? parse(angle) : null,
      },
      { onSuccess: () => setLength("") },
    );
  };

  return (
    <div className="stack">
      <div className="card">
        <div className="card__title">
          <h2>Длины маятника</h2>
          <span className="muted small">
            Основная серия: {experiment.main_periods} колебаний на замер
          </span>
        </div>
        {experiment.series.length === 0 ? (
          <p className="secondary">
            Добавьте длины, при которых будете проводить опыты. Для проверки зависимости T ~ √L
            удобно брать пары, отличающиеся в 4 раза (20 и 80 см, 25 и 100 см).
          </p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>L, см</th>
                  <th>σL, см</th>
                  <th>Ручных замеров (N = {experiment.main_periods})</th>
                  <th>T секундомер, с</th>
                  <th className="left">Видео</th>
                  <th>T камера, с</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {experiment.series.map((s) => {
                  const q = quickStats(s, experiment.main_periods);
                  return (
                    <tr key={s.id}>
                      <td>
                        <Link to={`series/${s.id}`}>
                          <strong>{num(s.length_cm, 1)}</strong>
                        </Link>
                      </td>
                      <td>{num(s.length_sigma_cm, 1)}</td>
                      <td>{q.trials || DASH}</td>
                      <td>{num(q.swMean, 4)}</td>
                      <td className="left">
                        <div className="row" style={{ gap: 4 }}>
                          {s.videos.length === 0 && DASH}
                          {s.videos.map((v) => (
                            <Link key={v.id} to={`videos/${v.id}`} title={v.original_name}>
                              <VideoStatusBadge video={v} />
                            </Link>
                          ))}
                        </div>
                      </td>
                      <td>{num(q.camMean, 5)}</td>
                      <td className="actions">
                        <div className="row" style={{ gap: 4, flexWrap: "nowrap" }}>
                          <Link className="button small" to={`series/${s.id}`}>
                            Открыть
                          </Link>
                          <button
                            className="small ghost danger"
                            title="Удалить длину вместе с замерами и видео"
                            onClick={() => {
                              if (confirm(`Удалить длину ${s.length_cm} см со всеми измерениями?`))
                                remove.mutate(s.id);
                            }}
                          >
                            Удалить
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <form className="card stack" onSubmit={submit}>
        <h3>Добавить длину</h3>
        <div className="form-row">
          <label className="field">
            Длина L, см (до центра груза)
            <input
              inputMode="decimal"
              value={length}
              onChange={(e) => setLength(e.target.value)}
              placeholder="60"
              required
            />
          </label>
          <label className="field">
            Погрешность σL, см
            <input inputMode="decimal" value={sigma} onChange={(e) => setSigma(e.target.value)} />
          </label>
          <label className="field">
            Угол отклонения, ° (необязательно)
            <input
              inputMode="decimal"
              value={angle}
              onChange={(e) => setAngle(e.target.value)}
              placeholder="5–7"
            />
          </label>
          <button className="primary" type="submit" disabled={!length || create.isPending}>
            Добавить
          </button>
        </div>
        <div className="row small">
          <span className="muted">Быстро:</span>
          {PRESET_LENGTHS.filter((l) => !existing.has(l)).map((l) => (
            <button
              key={l}
              type="button"
              className="small"
              disabled={create.isPending}
              onClick={() => create.mutate({ length_cm: l, length_sigma_cm: parse(sigma) || 0.3 })}
            >
              {l} см
            </button>
          ))}
        </div>
        {create.isError && <ErrorNotice error={create.error} />}
      </form>
    </div>
  );
}
