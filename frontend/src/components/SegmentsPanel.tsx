import { useState } from "react";

import { api } from "../api/client";
import { useSegmentMutations } from "../api/hooks";
import type { ExperimentDetail, Segment, Video } from "../api/types";
import { DASH, num, pm } from "../lib/format";
import { ErrorNotice } from "./Status";

interface Props {
  video: Video;
  experiment: ExperimentDetail;
  selectedId: number | null;
  onSelect: (id: number | null) => void;
}

const parse = (v: string) => Number(v.replace(",", "."));

/** Длина нити по периоду при малой амплитуде: L = g·T₀²/4π². */
function lengthFromPeriod(segment: Segment, g: number): number | null {
  const t0 = segment.result?.t0 ?? segment.result?.period;
  return t0 ? ((g * t0 * t0) / (4 * Math.PI * Math.PI)) * 100 : null;
}

export function SegmentsPanel({ video, experiment, selectedId, onSelect }: Props) {
  const mutations = useSegmentMutations(experiment.id, video.id);
  const [editing, setEditing] = useState<{ id: number; from: string; to: string } | null>(null);
  const [manual, setManual] = useState({ from: "", to: "" });
  const [creating, setCreating] = useState<number | null>(null);
  const [createError, setCreateError] = useState<unknown>(null);
  const error = mutations.update.error ?? mutations.create.error ?? mutations.remove.error ?? createError;

  const [newLength, setNewLength] = useState<{ segment: Segment; value: string } | null>(null);

  const assign = (segment: Segment, value: string) => {
    if (value === "new") {
      const guess = segment.result?.length_from_video_cm ?? lengthFromPeriod(segment, experiment.g_reference);
      setNewLength({ segment, value: guess ? num(guess, 1) : "" });
      return;
    }
    mutations.update.mutate({ id: segment.id, patch: { series_id: value ? Number(value) : null } });
  };

  const createSeries = async () => {
    if (!newLength || !(parse(newLength.value) > 0)) return;
    const { segment } = newLength;
    setCreating(segment.id);
    setCreateError(null);
    try {
      const series = await api.createSeries(experiment.id, { length_cm: parse(newLength.value) });
      await mutations.update.mutateAsync({ id: segment.id, patch: { series_id: series.id } });
      setNewLength(null);
    } catch (err) {
      setCreateError(err);
    } finally {
      setCreating(null);
    }
  };

  const saveBounds = () => {
    if (!editing) return;
    mutations.update.mutate(
      { id: editing.id, patch: { t_start: parse(editing.from), t_end: parse(editing.to) } },
      { onSuccess: () => setEditing(null) },
    );
  };

  return (
    <div className="stack">
      {video.segments.length === 0 ? (
        <p className="secondary small">Участков пока нет.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Время, с</th>
                <th>Колебаний</th>
                <th>T средний, с</th>
                <th>T₀ (малые колеб.), с</th>
                <th>Амплитуда</th>
                <th>L по T₀, см</th>
                <th className="left">Длина серии</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {video.segments.map((s, i) => {
                const r = s.result;
                const isEditing = editing?.id === s.id;
                return (
                  <tr
                    key={s.id}
                    className={s.excluded ? "excluded" : undefined}
                    style={s.id === selectedId ? { background: "var(--accent-soft)" } : undefined}
                  >
                    <td>
                      <button className="small ghost" onClick={() => onSelect(s.id === selectedId ? null : s.id)}>
                        {i + 1} {s.id === selectedId ? "▾" : "▸"}
                      </button>
                    </td>
                    <td>
                      {isEditing ? (
                        <span className="row" style={{ gap: 4, flexWrap: "nowrap" }}>
                          <input
                            style={{ width: 70 }}
                            value={editing.from}
                            onChange={(e) => setEditing({ ...editing, from: e.target.value })}
                          />
                          –
                          <input
                            style={{ width: 70 }}
                            value={editing.to}
                            onChange={(e) => setEditing({ ...editing, to: e.target.value })}
                          />
                          <button className="small primary" onClick={saveBounds}>
                            ✓
                          </button>
                          <button className="small ghost" onClick={() => setEditing(null)}>
                            ✕
                          </button>
                        </span>
                      ) : (
                        <span title={s.auto ? "найден автоматически" : "задан вручную"}>
                          {num(s.t_start, 1)}–{num(s.t_end, 1)}
                          {!s.auto && " ✎"}
                        </span>
                      )}
                    </td>
                    <td>{r ? num(r.periods_observed, 1) : DASH}</td>
                    <td>{r ? pm(r.period, r.period_se, 5) : <span className="badge badge--critical">! {s.error}</span>}</td>
                    <td>{r?.t0 ? pm(r.t0, r.t0_se, 5) : DASH}</td>
                    <td>
                      {r?.theta_max_deg != null
                        ? `${num(r.theta_max_deg, 0)}° → ${num(r.theta_min_deg, 0)}°`
                        : r
                          ? `${num(r.amplitude_start_px, 0)} px`
                          : DASH}
                    </td>
                    <td>{num(lengthFromPeriod(s, experiment.g_reference), 1)}</td>
                    <td className="left">
                      <select
                        value={s.series_id ?? ""}
                        disabled={creating === s.id || mutations.update.isPending}
                        onChange={(e) => assign(s, e.target.value)}
                        aria-label="Длина серии"
                      >
                        <option value="">— не привязан —</option>
                        {experiment.series.map((series) => (
                          <option key={series.id} value={series.id}>
                            L = {num(series.length_cm, 1)} см
                          </option>
                        ))}
                        <option value="new">+ новая длина…</option>
                      </select>
                    </td>
                    <td className="actions">
                      <div className="row" style={{ gap: 2, flexWrap: "nowrap" }}>
                        <button
                          className="small ghost icon"
                          title="Изменить границы"
                          aria-label="Изменить границы"
                          onClick={() => setEditing({ id: s.id, from: num(s.t_start, 2), to: num(s.t_end, 2) })}
                        >
                          ✎
                        </button>
                        <button
                          className="small ghost icon"
                          title={s.excluded ? "Вернуть в расчёт" : "Исключить из расчёта"}
                          aria-label={s.excluded ? "Вернуть в расчёт" : "Исключить из расчёта"}
                          onClick={() => mutations.update.mutate({ id: s.id, patch: { excluded: !s.excluded } })}
                        >
                          {s.excluded ? "↺" : "⊘"}
                        </button>
                        <button
                          className="small ghost danger icon"
                          title="Удалить участок"
                          aria-label="Удалить участок"
                          onClick={() => {
                            if (s.id === selectedId) onSelect(null);
                            mutations.remove.mutate(s.id);
                          }}
                        >
                          ✕
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

      {newLength && (
        <form
          className="notice stack"
          onSubmit={(e) => {
            e.preventDefault();
            void createSeries();
          }}
        >
          <div>
            Новая длина для участка {num(newLength.segment.t_start, 1)}–{num(newLength.segment.t_end, 1)} с.{" "}
            {newLength.segment.result?.length_from_video_cm != null
              ? "Подставлена длина нити по видео (дуга + масштаб)."
              : "Подставлена длина по периоду — это только подсказка: g по ней считать нельзя."}{" "}
            Введите длину, измеренную линейкой до центра груза.
          </div>
          <div className="form-row">
            <label className="field">
              L, см
              <input
                inputMode="decimal"
                autoFocus
                value={newLength.value}
                onChange={(e) => setNewLength({ ...newLength, value: e.target.value })}
              />
            </label>
            <button className="primary" type="submit" disabled={creating !== null || !(parse(newLength.value) > 0)}>
              Создать и привязать
            </button>
            <button type="button" onClick={() => setNewLength(null)}>
              Отмена
            </button>
          </div>
        </form>
      )}

      <form
        className="form-row"
        onSubmit={(e) => {
          e.preventDefault();
          mutations.create.mutate(
            { t_start: parse(manual.from), t_end: parse(manual.to) },
            { onSuccess: () => setManual({ from: "", to: "" }) },
          );
        }}
      >
        <label className="field">
          Свой участок: от, с
          <input inputMode="decimal" value={manual.from} onChange={(e) => setManual({ ...manual, from: e.target.value })} />
        </label>
        <label className="field">
          до, с
          <input inputMode="decimal" value={manual.to} onChange={(e) => setManual({ ...manual, to: e.target.value })} />
        </label>
        <button type="submit" disabled={!manual.from || !manual.to || mutations.create.isPending}>
          Добавить участок
        </button>
      </form>
      {error ? <ErrorNotice error={error} /> : null}
    </div>
  );
}
