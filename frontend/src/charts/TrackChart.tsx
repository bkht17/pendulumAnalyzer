import { useMemo } from "react";
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { TrackData, VideoResult } from "../api/types";
import { num } from "../lib/format";
import { LegendItem, TooltipBox } from "./ChartTooltip";
import { SERIES } from "./series";

const MAX_POINTS = 2000;

interface Props {
  track: TrackData;
  result: VideoResult | null;
}

/** Координата маркера от времени + подогнанная затухающая синусоида + моменты прохождения центра. */
export function TrackChart({ track, result }: Props) {
  const axis = result?.axis ?? "x";
  const data = useMemo(() => {
    const values = axis === "x" ? track.x : track.y;
    const step = Math.max(1, Math.ceil(track.t.length / MAX_POINTS));
    const fit = result?.fit;
    const rows: { t: number; pos: number | null; fit: number | null }[] = [];
    for (let i = 0; i < track.t.length; i += step) {
      const t = track.t[i]!;
      const tr = fit ? t - fit.t_ref : 0;
      rows.push({
        t,
        pos: values[i] ?? null,
        fit: fit
          ? fit.center +
            fit.amplitude * Math.exp(-fit.damping * tr) * Math.cos((2 * Math.PI * tr) / fit.period + fit.phase)
          : null,
      });
    }
    return rows;
  }, [track, result, axis]);

  const crossings = useMemo(
    () => (result ? result.crossing_times.map((t) => ({ t, pos: result.center_px })) : []),
    [result],
  );

  return (
    <div>
      <div className="chart-legend">
        <LegendItem color={SERIES.camera} label={`Положение маркера (${axis}, пиксели)`} kind="line" />
        {result?.fit && <LegendItem color={SERIES.fit} label="Затухающая синусоида (подгонка)" kind="dashed" />}
        {result && <LegendItem color={SERIES.theory} label="Прохождение равновесия" />}
      </div>
      <div className="chart">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 20, left: 4 }}>
            <CartesianGrid stroke={SERIES.grid} vertical={false} />
            <XAxis
              dataKey="t"
              type="number"
              domain={[(min: number) => Math.floor(min), (max: number) => Math.ceil(max)]}
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
            {result && <ReferenceLine y={result.center_px} stroke={SERIES.axis} />}
            <Tooltip
              content={({ active, payload }) => {
                const row = payload?.[0]?.payload as (typeof data)[number] | undefined;
                if (!active || !row || row.pos === undefined) return null;
                return (
                  <TooltipBox
                    title={`t = ${num(row.t, 3)} с`}
                    rows={[
                      { color: SERIES.camera, label: "Маркер", value: `${num(row.pos, 1)} px` },
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
