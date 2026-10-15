import {
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { VideoResult } from "../api/types";
import { num } from "../lib/format";
import { LegendItem, TooltipBox } from "./ChartTooltip";
import { SERIES } from "./series";

/** Каждый отдельный период по видео: видно и случайный разброс, и медленный дрейф с амплитудой. */
export function PeriodsChart({ result }: { result: VideoResult }) {
  const data = result.period_values.map((value, i) => ({
    t: result.period_value_times[i] ?? 0,
    ms: (value - result.period) * 1000,
    value,
  }));
  if (data.length === 0) return null;

  return (
    <div>
      <div className="chart-legend">
        <LegendItem color={SERIES.camera} label="Отдельный период минус средний, мс" />
        <LegendItem color={SERIES.theory} label={`Средний T = ${num(result.period, 5)} с`} kind="line" />
      </div>
      <div className="chart">
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 8, right: 12, bottom: 20, left: 4 }}>
            <CartesianGrid stroke={SERIES.grid} vertical={false} />
            <XAxis
              dataKey="t"
              type="number"
              domain={["dataMin", "dataMax"]}
              tickFormatter={(v: number) => num(v, 0)}
              stroke={SERIES.axis}
              label={{ value: "t, с", position: "insideBottomRight", offset: -12 }}
            />
            <YAxis
              dataKey="ms"
              type="number"
              width={52}
              tickFormatter={(v: number) => num(v, 1)}
              stroke={SERIES.axis}
            />
            <ReferenceLine y={0} stroke={SERIES.theory} strokeWidth={1.5} />
            <Tooltip
              cursor={false}
              content={({ active, payload }) => {
                const row = payload?.[0]?.payload as (typeof data)[number] | undefined;
                if (!active || !row) return null;
                return (
                  <TooltipBox
                    title={`t ≈ ${num(row.t, 2)} с`}
                    rows={[
                      { color: SERIES.camera, label: "Период", value: `${num(row.value, 4)} с` },
                      { label: "Отклонение", value: `${num(row.ms, 2)} мс` },
                    ]}
                  />
                );
              }}
            />
            <Scatter data={data} fill={SERIES.camera} isAnimationActive={false} />
          </ScatterChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
