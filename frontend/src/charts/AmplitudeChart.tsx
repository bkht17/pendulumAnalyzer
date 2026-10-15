import { useMemo } from "react";
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { SegmentResult } from "../api/types";
import { num, pm } from "../lib/format";
import { amplitudeFactor } from "../lib/physics";
import { LegendItem, TooltipBox } from "./ChartTooltip";
import { SERIES } from "./series";

interface Point {
  theta: number;
  dt: number;
  period: number;
}

/**
 * Отдельные периоды против амплитуды: превышение над T₀ (мс). Теория — T₀·(1 + θ²/16 + …);
 * если точки ложатся на кривую, поправка на амплитуду подтверждена экспериментально.
 */
export function AmplitudeChart({ result }: { result: SegmentResult }) {
  const t0 = result.t0;
  const { points, theory, fit } = useMemo(() => {
    if (t0 === null) return { points: [], theory: [], fit: [] };
    const pts: Point[] = result.period_values.map((period, i) => ({
      theta: result.period_amplitudes_deg[i] ?? 0,
      dt: (period - t0) * 1000,
      period,
    }));
    const thetas = pts.map((p) => p.theta);
    const lo = Math.max(0, Math.min(...thetas) - 2);
    const hi = Math.max(...thetas) + 2;
    const grid = Array.from({ length: 40 }, (_, i) => lo + ((hi - lo) * i) / 39);
    const k = result.amplitude_k;
    const rad2 = (deg: number) => ((deg * Math.PI) / 180) ** 2;
    // Свободная подгонка T = a·(1 + k·θ²): свой свободный член a, а не T₀ серии.
    const a =
      k === null
        ? t0
        : pts.reduce((sum, p) => sum + p.period, 0) / pts.reduce((sum, p) => sum + 1 + k * rad2(p.theta), 0);
    return {
      points: pts,
      theory: grid.map((theta) => ({ theta, dt: t0 * (amplitudeFactor(theta) - 1) * 1000 })),
      fit: k === null ? [] : grid.map((theta) => ({ theta, dt: (a * (1 + k * rad2(theta)) - t0) * 1000 })),
    };
  }, [result, t0]);

  if (t0 === null || points.length === 0) {
    return (
      <p className="muted small">
        Угол амплитуды не определён: отметьте точку подвеса или масштаб, либо амплитуда слишком мала,
        чтобы найти подвес по дуге.
      </p>
    );
  }

  return (
    <div>
      <div className="chart-legend">
        <LegendItem color={SERIES.camera} label="Отдельные периоды" />
        <LegendItem color={SERIES.theory} label="Теория T₀(1 + θ²/16 + …)" kind="dashed" />
        {fit.length > 0 && (
          <LegendItem
            color={SERIES.fit}
            label={`Подгонка: k = ${pm(result.amplitude_k, result.amplitude_k_se)} (теория 0,0625)`}
            kind="line"
          />
        )}
      </div>
      <div className="chart">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart margin={{ top: 8, right: 16, bottom: 24, left: 8 }}>
            <CartesianGrid stroke={SERIES.grid} vertical={false} />
            <XAxis
              dataKey="theta"
              type="number"
              domain={["dataMin", "dataMax"]}
              stroke={SERIES.axis}
              tickFormatter={(v: number) => `${num(v, 0)}°`}
              label={{ value: "амплитуда θ", position: "insideBottomRight", offset: -14 }}
            />
            <YAxis
              type="number"
              domain={["auto", "auto"]}
              width={56}
              stroke={SERIES.axis}
              tickFormatter={(v: number) => num(v, 1)}
              label={{ value: "T − T₀, мс", angle: -90, position: "insideLeft" }}
            />
            <Tooltip
              cursor={false}
              content={({ active, payload }) => {
                const row = payload?.[0]?.payload as Point | undefined;
                if (!active || !row || row.period === undefined) return null;
                return (
                  <TooltipBox
                    title={`θ = ${num(row.theta, 1)}°`}
                    rows={[
                      { color: SERIES.camera, label: "Период", value: `${num(row.period, 5)} с` },
                      { label: "T − T₀", value: `${num(row.dt, 2)} мс` },
                    ]}
                  />
                );
              }}
            />
            <Line data={theory} dataKey="dt" stroke={SERIES.theory} strokeDasharray="5 4" strokeWidth={1.5} dot={false} isAnimationActive={false} />
            {fit.length > 0 && (
              <Line data={fit} dataKey="dt" stroke={SERIES.fit} strokeWidth={1.5} dot={false} isAnimationActive={false} />
            )}
            <Scatter data={points} dataKey="dt" fill={SERIES.camera} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <p className="muted small" style={{ margin: 0 }}>
        T₀ = {pm(t0, result.t0_se)} с — период при малых колебаниях. Длина нити для пересчёта амплитуды в
        угол: {result.length_px_source === "arc" ? "по дуге траектории (подвес найден автоматически)" : result.length_px_source === "pivot" ? "от отмеченной точки подвеса" : "по масштабу и записанной длине"}.
      </p>
    </div>
  );
}
