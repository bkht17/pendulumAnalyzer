import { useMemo } from "react";
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { Segment, TrackData } from "../api/types";
import { num } from "../lib/format";
import { LegendItem, TooltipBox } from "./ChartTooltip";
import { SERIES } from "./series";

const MAX_POINTS = 2500;
const ZOOM_MARGIN_S = 1;

interface Props {
  track: TrackData;
  axis: "x" | "y";
  segments: Segment[];
  selected: Segment | null;
  onSelect?: (id: number) => void;
}

interface Row {
  t: number;
  pos: number | null;
  fit: number | null;
}

/**
 * Координата груза от времени. Без выбранного участка — вся запись (участки подсвечены),
 * с выбранным — он крупно, с подогнанной синусоидой и моментами прохождения центра.
 */
export function TrackChart({ track, axis, segments, selected, onSelect }: Props) {
  const range: [number, number] | null = selected
    ? [selected.t_start - ZOOM_MARGIN_S, selected.t_end + ZOOM_MARGIN_S]
    : null;
  const result = selected?.result ?? null;

  const data = useMemo(() => {
    const values = axis === "x" ? track.x : track.y;
    const lo = selected ? selected.t_start - ZOOM_MARGIN_S : -Infinity;
    const hi = selected ? selected.t_end + ZOOM_MARGIN_S : Infinity;
    const idx: number[] = [];
    for (let i = 0; i < track.t.length; i++) {
      const t = track.t[i]!;
      if (t >= lo && t <= hi) idx.push(i);
    }
    const step = Math.max(1, Math.ceil(idx.length / MAX_POINTS));
    const fit = selected?.result?.fit;
    const rows: Row[] = [];
    for (let j = 0; j < idx.length; j += step) {
      const i = idx[j]!;
      const t = track.t[i]!;
      const inside = selected && t >= selected.t_start && t <= selected.t_end;
      const tr = fit ? t - fit.t_ref : 0;
      rows.push({
        t,
        pos: values[i] ?? null,
        fit:
          fit && inside
            ? fit.center + fit.amplitude * Math.exp(-fit.damping * tr) * Math.cos((2 * Math.PI * tr) / fit.period + fit.phase)
            : null,
      });
    }
    return rows;
  }, [track, axis, selected]);

  const crossings = useMemo(
    () => (result ? result.crossing_times.map((t) => ({ t, pos: result.center_px })) : []),
    [result],
  );

  return (
    <div>
      <div className="chart-legend">
        <LegendItem color={SERIES.camera} label={`Положение груза (${axis}, пиксели)`} kind="line" />
        {result?.fit && <LegendItem color={SERIES.fit} label="Затухающая синусоида (подгонка)" kind="dashed" />}
        {result && <LegendItem color={SERIES.theory} label="Прохождение равновесия" />}
        {!selected && segments.length > 0 && (
          <span>
            <span className="swatch" style={{ background: "var(--accent-soft)", border: "1px solid var(--accent)" }} />
            Найденные серии колебаний{onSelect ? " (клик — открыть)" : ""}
          </span>
        )}
      </div>
      <div className="chart">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 20, left: 4 }}>
            <CartesianGrid stroke={SERIES.grid} vertical={false} />
            <XAxis
              dataKey="t"
              type="number"
              domain={range ?? [(min: number) => Math.floor(min), (max: number) => Math.ceil(max)]}
              allowDataOverflow
              allowDecimals={false}
              tickFormatter={(v: number) => num(v, 0)}
              stroke={SERIES.axis}
              label={{ value: "t, с", position: "insideBottomRight", offset: -12 }}
            />
            <YAxis
              type="number"
              domain={["auto", "auto"]}
              width={52}
              tickFormatter={(v: number) => num(v, 0)}
              stroke={SERIES.axis}
            />
            {!selected &&
              segments.map((s) => (
                <ReferenceArea
                  key={s.id}
                  x1={s.t_start}
                  x2={s.t_end}
                  fill="var(--accent)"
                  fillOpacity={s.excluded ? 0.04 : 0.12}
                  stroke="none"
                  onClick={onSelect ? () => onSelect(s.id) : undefined}
                  style={onSelect ? { cursor: "pointer" } : undefined}
                />
              ))}
            {result && <ReferenceLine y={result.center_px} stroke={SERIES.axis} />}
            <Tooltip
              content={({ active, payload }) => {
                const row = payload?.[0]?.payload as Row | undefined;
                if (!active || !row || row.pos === undefined) return null;
                return (
                  <TooltipBox
                    title={`t = ${num(row.t, 3)} с`}
                    rows={[
                      { color: SERIES.camera, label: "Груз", value: `${num(row.pos, 1)} px` },
                      ...(row.fit !== null ? [{ color: SERIES.fit, label: "Подгонка", value: `${num(row.fit, 1)} px` }] : []),
                    ]}
                  />
                );
              }}
            />
            <Line dataKey="pos" stroke={SERIES.camera} strokeWidth={1.5} dot={false} isAnimationActive={false} connectNulls={false} />
            {result?.fit && (
              <Line dataKey="fit" stroke={SERIES.fit} strokeWidth={2} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
            )}
            {crossings.length > 0 && (
              <Scatter data={crossings} dataKey="pos" fill={SERIES.theory} shape="circle" isAnimationActive={false} />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
