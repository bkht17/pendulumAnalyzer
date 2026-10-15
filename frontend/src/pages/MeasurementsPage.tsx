import { type FormEvent, useState } from "react";
import { Link } from "react-router";

import { useSeriesMutations } from "../api/hooks";
import type { Series } from "../api/types";
import { ErrorNotice } from "../components/Status";
import { EquivalentLength } from "../components/EquivalentLength";
import { LengthEditor } from "../components/LengthEditor";
import { VideosCard } from "../components/VideosCard";
import { DASH, num } from "../lib/format";
import { useExperimentContext } from "./experimentContext";

const PRESET_LENGTHS = [20, 25, 40, 60, 80, 100];

function quickStats(series: Series, mainPeriods: number) {
  const trials = series.trials.filter((t) => !t.excluded && t.periods === mainPeriods);
  const swMean = trials.length ? trials.reduce((a, t) => a + t.period_s, 0) / trials.length : null;
  const done = series.segments.filter((s) => !s.excluded && s.result);
  const mean = (values: number[]) => (values.length ? values.reduce((a, v) => a + v, 0) / values.length : null);
  return {
    trials: trials.length,
    swMean,
    camMean: mean(done.map((s) => s.result!.period)),
    camT0: mean(done.flatMap((s) => (s.result!.t0 ? [s.result!.t0] : []))),
    segments: done.length,
  };
}

export function MeasurementsPage() {
  const { experiment } = useExperimentContext();
  const { create, update, remove } = useSeriesMutations(experiment.id);
  const [editingId, setEditingId] = useState<number | null>(null);
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
                  <th>Участков видео</th>
                  <th>T камера, с</th>
                  <th>T₀ камера, с</th>
                  <th title="Длина идеального маятника с таким T₀: L = g·T₀²/4π². Не измерение, а оценка по периоду">
                    L по периоду, см
                  </th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {experiment.series.map((s) => {
                  const q = quickStats(s, experiment.main_periods);
                  return (
                    <tr key={s.id}>
                      {editingId === s.id ? (
                        <td colSpan={2}>
                          <LengthEditor
                            series={s}
                            busy={update.isPending}
                            onCancel={() => setEditingId(null)}
                            onSave={(patch) =>
                              update.mutate({ id: s.id, patch }, { onSuccess: () => setEditingId(null) })
                            }
                          />
                        </td>
                      ) : (
                        <>
                          <td>
                            <Link to={`series/${s.id}`}>
                              <strong>{num(s.length_cm, 1)}</strong>
                            </Link>
                          </td>
                          <td>{num(s.length_sigma_cm, 1)}</td>
                        </>
                      )}
                      <td>{q.trials || DASH}</td>
                      <td>{num(q.swMean, 4)}</td>
                      <td>{q.segments || DASH}</td>
                      <td>{num(q.camMean, 5)}</td>
                      <td>{num(q.camT0, 5)}</td>
                      <td>
                        <EquivalentLength t0={q.camT0} g={experiment.g_reference} measured={s.length_cm} />
                      </td>
                      <td className="actions">
                        <div className="row" style={{ gap: 4, flexWrap: "nowrap" }}>
                          <Link className="button small" to={`series/${s.id}`}>
                            Открыть
                          </Link>
                          <button
                            className="small ghost icon"
                            title="Исправить длину"
                            aria-label="Исправить длину"
                            onClick={() => setEditingId(s.id)}
                          >
                            ✎
                          </button>
                          <button
                            className="small ghost danger"
                            title="Удалить длину вместе с ручными замерами (видео останутся, участки отвяжутся)"
                            onClick={() => {
                              if (confirm(`Удалить длину ${s.length_cm} см и её ручные замеры?`))
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

      <VideosCard experiment={experiment} />

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
