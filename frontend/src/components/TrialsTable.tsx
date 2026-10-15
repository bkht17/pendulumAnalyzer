import { type FormEvent, useMemo, useState } from "react";

import type { Trial, TrialInput } from "../api/types";
import { DASH, num } from "../lib/format";

interface Props {
  trials: Trial[];
  mainPeriods: number;
  busy: boolean;
  onAdd: (input: TrialInput) => void;
  onToggle: (trial: Trial) => void;
  onDelete: (trial: Trial) => void;
}

function stats(values: number[]) {
  if (values.length === 0) return null;
  const mean = values.reduce((a, v) => a + v, 0) / values.length;
  const std =
    values.length > 1
      ? Math.sqrt(values.reduce((a, v) => a + (v - mean) ** 2, 0) / (values.length - 1))
      : null;
  return { mean, std, n: values.length };
}

export function TrialsTable({ trials, mainPeriods, busy, onAdd, onToggle, onDelete }: Props) {
  const [periods, setPeriods] = useState(String(mainPeriods));
  const [time, setTime] = useState("");

  const groups = useMemo(() => {
    const byN = new Map<number, number[]>();
    for (const t of trials) {
      if (t.excluded) continue;
      byN.set(t.periods, [...(byN.get(t.periods) ?? []), t.period_s]);
    }
    return [...byN.entries()]
      .sort(([a], [b]) => a - b)
      .map(([periods, values]) => ({ periods, ...stats(values)! }));
  }, [trials]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const total = Number(time.replace(",", "."));
    const n = Number(periods);
    if (!(total > 0) || !(n >= 1)) return;
    onAdd({ periods: n, total_time_s: total, source: "manual" });
    setTime("");
  };

  return (
    <div className="stack">
      <form className="form-row" onSubmit={submit}>
        <label className="field">
          N колебаний
          <input inputMode="numeric" value={periods} onChange={(e) => setPeriods(e.target.value)} />
        </label>
        <label className="field">
          Время t, с (с внешнего секундомера)
          <input
            inputMode="decimal"
            value={time}
            onChange={(e) => setTime(e.target.value)}
            placeholder="15,62"
          />
        </label>
        <button type="submit" disabled={!time || busy}>
          Добавить
        </button>
      </form>

      {groups.length > 0 && (
        <div className="row small secondary">
          {groups.map((g) => (
            <span key={g.periods} className="badge">
              N = {g.periods}: T̄ = {num(g.mean, 4)} с, σ = {g.std === null ? DASH : num(g.std, 4)} с
              (n = {g.n})
            </span>
          ))}
        </div>
      )}

      {trials.length === 0 ? (
        <p className="muted small">Замеров пока нет.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>N</th>
                <th>t, с</th>
                <th>T = t/N, с</th>
                <th className="left">Кто</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {trials.map((t, i) => (
                <tr key={t.id} className={t.excluded ? "excluded" : undefined}>
                  <td>{i + 1}</td>
                  <td>{t.periods}</td>
                  <td>{num(t.total_time_s, 2)}</td>
                  <td>
                    {num(t.period_s, 4)}{" "}
                    {t.suspected_outlier && !t.excluded && (
                      <span
                        className="badge badge--warn"
                        title="Сильно отличается от остальных — возможно, сбились со счёта колебаний"
                      >
                        ! выброс?
                      </span>
                    )}
                  </td>
                  <td className="left secondary" title={t.source === "app" ? "встроенный секундомер" : "введено вручную"}>
                    {t.operator || DASH}
                    {t.source === "app" ? " ⏱" : ""}
                  </td>
                  <td className="actions">
                    <div className="row" style={{ gap: 2, flexWrap: "nowrap" }}>
                      <button
                        className="small ghost icon"
                        title={t.excluded ? "Вернуть в расчёт" : "Исключить из расчёта"}
                        aria-label={t.excluded ? "Вернуть в расчёт" : "Исключить из расчёта"}
                        onClick={() => onToggle(t)}
                      >
                        {t.excluded ? "↺" : "⊘"}
                      </button>
                      <button
                        className="small ghost danger icon"
                        title="Удалить замер"
                        aria-label="Удалить замер"
                        onClick={() => onDelete(t)}
                      >
                        ✕
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
