import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api/client";
import { keys, useSegmentMutations } from "../api/hooks";
import type { ExperimentDetail, Segment, Video } from "../api/types";
import { DASH, num, pm } from "../lib/format";
import { parseLengths } from "../lib/lengths";
import { equivalentLength } from "../lib/physics";
import { EquivalentLength } from "./EquivalentLength";
import { ErrorNotice } from "./Status";

interface Props {
  video: Video;
  experiment: ExperimentDetail;
  selectedId: number | null;
  onSelect: (id: number | null) => void;
}

const parse = (v: string) => Number(v.replace(",", "."));

const periodOf = (segment: Segment) => segment.result?.t0 ?? segment.result?.period ?? null;

export function SegmentsPanel({ video, experiment, selectedId, onSelect }: Props) {
  const mutations = useSegmentMutations(experiment.id, video.id);
  const client = useQueryClient();
  const invalidateExperiment = () => client.invalidateQueries({ queryKey: keys.experiment(experiment.id) });
  const [editing, setEditing] = useState<{ id: number; from: string; to: string } | null>(null);
  const [manual, setManual] = useState({ from: "", to: "" });
  const [creating, setCreating] = useState<number | null>(null);
  const [createError, setCreateError] = useState<unknown>(null);
  const error =
    mutations.update.error ?? mutations.create.error ?? mutations.remove.error ?? mutations.autoAssign.error ?? createError;
  const [autoResult, setAutoResult] = useState<string | null>(null);
  const lengthOf = (id: number | null) => experiment.series.find((x) => x.id === id)?.length_cm ?? null;
  const unassigned = video.segments.filter((x) => x.series_id === null && !x.excluded && x.result).length;

  const [lengthsInput, setLengthsInput] = useState("");
  const [addingLengths, setAddingLengths] = useState(false);
  const addLengths = async () => {
    const existing = new Set(experiment.series.map((x) => x.length_cm));
    const values = parseLengths(lengthsInput).filter((v) => !existing.has(v));
    if (values.length === 0) return;
    setAddingLengths(true);
    setCreateError(null);
    try {
      for (const length_cm of values) await api.createSeries(experiment.id, { length_cm });
      setLengthsInput("");
      await invalidateExperiment();
    } catch (err) {
      setCreateError(err);
    } finally {
      setAddingLengths(false);
    }
  };

  const runAutoAssign = () => {
    const before = new Set(video.segments.filter((x) => x.series_id !== null).map((x) => x.id));
    mutations.autoAssign.mutate(undefined, {
      onSuccess: (updated) => {
        const linked = updated.segments.filter((x) => x.series_id !== null && !before.has(x.id)).length;
        const left = updated.segments.filter((x) => x.series_id === null && !x.excluded).length;
        setAutoResult(
          `Привязано по периоду: ${linked}.` +
            (left ? ` Не привязано: ${left} — ни одна длина не подходит однозначно, выберите вручную.` : ""),
        );
      },
    });
  };

  const [newLength, setNewLength] = useState<{ segment: Segment; value: string } | null>(null);

  const assign = (segment: Segment, value: string) => {
    if (value === "new") {
      // Поле пустое: длину задаёт человек по линейке. Оценки по видео и по периоду —
      // только подсказки рядом с полем, а не готовое значение.
      setNewLength({ segment, value: "" });
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
    const original = video.segments.find((x) => x.id === editing.id);
    const unchanged =
      original &&
      Math.abs(parse(editing.from) - original.t_start) < 0.01 &&
      Math.abs(parse(editing.to) - original.t_end) < 0.01;
    if (unchanged) return setEditing(null); // ничего не меняли — участок остаётся автоматическим
    mutations.update.mutate(
      { id: editing.id, patch: { t_start: parse(editing.from), t_end: parse(editing.to) } },
      { onSuccess: () => setEditing(null) },
    );
  };

  return (
    <div className="stack">
      {video.segments.length > 0 && (
        <div className="row">
          <button
            onClick={runAutoAssign}
            disabled={!unassigned || experiment.series.length === 0 || mutations.autoAssign.isPending}
            title={
              experiment.series.length === 0
                ? "Сначала добавьте длины (вкладка «Измерения»)"
                : "Каждый непривязанный участок — к длине, теоретический период которой ближе всего к T₀"
            }
          >
            Привязать по периоду
          </button>
          <span className="muted small">
            {experiment.series.length === 0
              ? "Сначала добавьте длины, измеренные линейкой:"
              : `Длины: ${experiment.series.map((x) => num(x.length_cm, 1)).join("; ")} см`}
          </span>
          <span className="spacer" />
          <form
            className="row"
            style={{ gap: 4 }}
            onSubmit={(e) => {
              e.preventDefault();
              void addLengths();
            }}
          >
            <input
              aria-label="Добавить длины, см"
              placeholder="60 40 20"
              style={{ width: 120 }}
              value={lengthsInput}
              onChange={(e) => setLengthsInput(e.target.value)}
            />
            <button type="submit" className="small" disabled={addingLengths || parseLengths(lengthsInput).length === 0}>
              Добавить длины
            </button>
          </form>
        </div>
      )}
      {autoResult && <div className="notice">{autoResult}</div>}
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
                <th title="Длина идеального маятника с таким T₀: L = g·T₀²/4π². Это не измерение, а оценка по периоду; в скобках — отличие от длины серии">
                  L по периоду, см
                </th>
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
                    <td>
                      <EquivalentLength t0={periodOf(s)} g={experiment.g_reference} measured={lengthOf(s.series_id)} />
                    </td>
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
            Новая длина для участка {num(newLength.segment.t_start, 1)}–{num(newLength.segment.t_end, 1)} с. Введите
            длину, измеренную линейкой.{" "}
            <span className="muted">
              Для сверки: по периоду ≈{" "}
              {num(periodOf(newLength.segment) && equivalentLength(periodOf(newLength.segment)!, experiment.g_reference), 1)} см
              {newLength.segment.result?.length_from_video_cm != null &&
                `, по видео (дуга + масштаб) ≈ ${num(newLength.segment.result.length_from_video_cm, 1)} см`}
              . Эффективная длина обычно на 1–3 см больше измеренной — это нормально.
            </span>
          </div>
          <div className="form-row">
            <label className="field">
              L, см
              <input
                inputMode="decimal"
                autoFocus
                placeholder="например, 60"
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
