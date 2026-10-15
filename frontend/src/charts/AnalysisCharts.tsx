import { useMemo } from "react";
import {
  CartesianGrid,
  ComposedChart,
  ErrorBar,
  Line,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { Analysis } from "../api/types";
import { ms, num, pm } from "../lib/format";
import { amplitudeFactor, logspace } from "../lib/physics";
import { logDomain, logTicks } from "./logScale";
import { LegendItem, TooltipBox, type TooltipRow } from "./ChartTooltip";
import { SERIES } from "./series";

const MARGIN = { top: 8, right: 16, bottom: 24, left: 8 };

function lengthDomain(analysis: Analysis): [number, number] {
  const lengths = analysis.series.map((s) => s.length_cm);
  return [0, Math.ceil((Math.max(...lengths, 20) * 1.1) / 10) * 10];
}

/** Сдвиг точек методов по горизонтали, чтобы совпадающие значения не закрывали друг друга. */
const DODGE_CM = 1.2;

interface PointRow {
  x: number;
  L: number;
  T: number;
  err: number;
  method: "stopwatch" | "camera";
}

function MethodLegend({ theory }: { theory: string }) {
  return (
    <div className="chart-legend">
      <LegendItem color={SERIES.camera} label="Камера" />
      <LegendItem color={SERIES.stopwatch} label="Секундомер" />
      <LegendItem color={SERIES.theory} label={theory} kind="dashed" />
    </div>
  );
}

const pointTooltip =
  (unit: string, digits: number) =>
  ({ active, payload }: { active?: boolean; payload?: readonly { payload?: unknown }[] }) => {
    const row = payload?.[0]?.payload as PointRow | undefined;
    if (!active || !row || row.method === undefined) return null;
    const rows: TooltipRow[] = [
      {
        color: row.method === "camera" ? SERIES.camera : SERIES.stopwatch,
        label: row.method === "camera" ? "Камера" : "Секундомер",
        value: `${pm(row.T, row.err || null, digits)} ${unit}`,
      },
    ];
    return <TooltipBox title={`L = ${num(row.L, 1)} см`} rows={rows} />;
  };

/** T(L): экспериментальные точки обоих методов и кривая 2π√(L/g). */
export function PeriodVsLengthChart({ analysis }: { analysis: Analysis }) {
  const domain = lengthDomain(analysis);
  const { stopwatch, camera, theory } = useMemo(() => {
    const sw: PointRow[] = [];
    const cam: PointRow[] = [];
    for (const s of analysis.series) {
      if (s.stopwatch)
        sw.push({ x: s.length_cm - DODGE_CM, L: s.length_cm, T: s.stopwatch.summary.mean, err: s.stopwatch.summary.sem ?? 0, method: "stopwatch" });
      if (s.camera) cam.push({ x: s.length_cm + DODGE_CM, L: s.length_cm, T: s.camera.period.value, err: s.camera.period.sigma ?? 0, method: "camera" });
    }
    const curve = Array.from({ length: 61 }, (_, i) => {
      const L = domain[0] + ((domain[1] - domain[0]) * i) / 60;
      return { x: L, theory: 2 * Math.PI * Math.sqrt(L / 100 / analysis.g_reference) };
    });
    return { stopwatch: sw, camera: cam, theory: curve };
  }, [analysis, domain]);

  return (
    <div>
      <MethodLegend theory={`Теория 2π√(L/g), g = ${num(analysis.g_reference, 2)}`} />
      <div className="chart chart--tall">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart margin={MARGIN}>
            <CartesianGrid stroke={SERIES.grid} vertical={false} />
            <XAxis dataKey="x" type="number" domain={domain} stroke={SERIES.axis} label={{ value: "L, см", position: "insideBottomRight", offset: -14 }} />
            <YAxis type="number" domain={[0, (max: number) => Math.ceil(max * 2) / 2]} tickCount={6} width={44} stroke={SERIES.axis} tickFormatter={(v: number) => num(v, 1)} label={{ value: "T, с", angle: -90, position: "insideLeft" }} />
            <Tooltip content={pointTooltip("с", 4)} cursor={false} />
            <Line data={theory} dataKey="theory" stroke={SERIES.theory} strokeDasharray="5 4" strokeWidth={1.5} dot={false} isAnimationActive={false} />
            <Scatter data={stopwatch} dataKey="T" fill={SERIES.stopwatch} isAnimationActive={false}>
              <ErrorBar dataKey="err" direction="y" width={6} stroke={SERIES.stopwatch} />
            </Scatter>
            <Scatter data={camera} dataKey="T" fill={SERIES.camera} shape="diamond" isAnimationActive={false}>
              <ErrorBar dataKey="err" direction="y" width={6} stroke={SERIES.camera} />
            </Scatter>
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/** T²(L) с аппроксимирующими прямыми: наклон даёт g, отрезок — неучтённую добавку к длине. */
export function PeriodSquaredChart({ analysis }: { analysis: Analysis }) {
  const domain = lengthDomain(analysis);
  const data = useMemo(() => {
    // Как и на сервере, приводим период к малой амплитуде: T₀ = T / f(θ).
    const t0 = (s: Analysis["series"][number], T: number) => T / amplitudeFactor(s.theory.amplitude_deg);
    const sw: PointRow[] = [];
    const cam: PointRow[] = [];
    for (const s of analysis.series) {
      if (s.stopwatch) {
        const T = t0(s, s.stopwatch.summary.mean);
        sw.push({ x: s.length_cm - DODGE_CM, L: s.length_cm, T: T * T, err: 2 * T * (s.stopwatch.summary.sem ?? 0), method: "stopwatch" });
      }
      if (s.camera) {
        const T = t0(s, s.camera.period.value);
        cam.push({ x: s.length_cm + DODGE_CM, L: s.length_cm, T: T * T, err: 2 * T * (s.camera.period.sigma ?? 0), method: "camera" });
      }
    }
    const line = (k: number, b: number) => [
      { x: domain[0], y: (k * domain[0]) / 100 + b },
      { x: domain[1], y: (k * domain[1]) / 100 + b },
    ];
    const theoryK = (4 * Math.PI ** 2) / analysis.g_reference;
    return {
      sw,
      cam,
      theory: line(theoryK, 0),
      fitCam: analysis.fit_camera ? line(analysis.fit_camera.slope, analysis.fit_camera.intercept) : null,
      fitSw: analysis.fit_stopwatch ? line(analysis.fit_stopwatch.slope, analysis.fit_stopwatch.intercept) : null,
    };
  }, [analysis, domain]);

  return (
    <div>
      <div className="chart-legend">
        <LegendItem color={SERIES.camera} label="Камера + прямая МНК" />
        <LegendItem color={SERIES.stopwatch} label="Секундомер + прямая МНК" />
        <LegendItem color={SERIES.theory} label="Теория T² = 4π²L/g" kind="dashed" />
      </div>
      <div className="chart chart--tall">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart margin={MARGIN}>
            <CartesianGrid stroke={SERIES.grid} vertical={false} />
            <XAxis dataKey="x" type="number" domain={domain} stroke={SERIES.axis} label={{ value: "L, см", position: "insideBottomRight", offset: -14 }} />
            <YAxis type="number" domain={[0, (max: number) => Math.ceil(max)]} tickCount={6} width={44} stroke={SERIES.axis} tickFormatter={(v: number) => num(v, 1)} label={{ value: "T², с²", angle: -90, position: "insideLeft" }} />
            <Tooltip content={pointTooltip("с²", 4)} cursor={false} />
            <Line data={data.theory} dataKey="y" stroke={SERIES.theory} strokeDasharray="5 4" strokeWidth={1.5} dot={false} isAnimationActive={false} />
            {data.fitSw && <Line data={data.fitSw} dataKey="y" stroke={SERIES.stopwatch} strokeWidth={1.5} dot={false} isAnimationActive={false} />}
            {data.fitCam && <Line data={data.fitCam} dataKey="y" stroke={SERIES.camera} strokeWidth={1.5} dot={false} isAnimationActive={false} />}
            <Scatter data={data.sw} dataKey="T" fill={SERIES.stopwatch} isAnimationActive={false}>
              <ErrorBar dataKey="err" direction="y" width={6} stroke={SERIES.stopwatch} />
            </Scatter>
            <Scatter data={data.cam} dataKey="T" fill={SERIES.camera} shape="diamond" isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

interface SpreadRow {
  x: number;
  L: number;
  sigma: number;
  method: "stopwatch" | "camera";
}

/** Разброс одного замера N колебаний для каждого метода. Логарифмическая шкала: разница ~100×. */
export function SpreadChart({ analysis }: { analysis: Analysis }) {
  const domain = lengthDomain(analysis);
  const { sw, cam } = useMemo(() => {
    const sw: SpreadRow[] = [];
    const cam: SpreadRow[] = [];
    for (const s of analysis.series) {
      if (s.stopwatch?.summary.std) sw.push({ x: s.length_cm, L: s.length_cm, sigma: s.stopwatch.summary.std, method: "stopwatch" });
      if (s.camera?.equivalent_std) cam.push({ x: s.length_cm, L: s.length_cm, sigma: s.camera.equivalent_std, method: "camera" });
    }
    return { sw, cam };
  }, [analysis]);
  const yDomain = logDomain([...sw, ...cam].map((r) => r.sigma));
  if (sw.length + cam.length === 0) return <p className="muted small">Недостаточно данных: нужны повторные замеры и обработанные видео.</p>;

  return (
    <div>
      <div className="chart-legend">
        <LegendItem color={SERIES.camera} label="Камера" />
        <LegendItem color={SERIES.stopwatch} label="Секундомер" />
      </div>
      <div className="chart">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart margin={MARGIN}>
            <CartesianGrid stroke={SERIES.grid} vertical={false} />
            <XAxis dataKey="x" type="number" domain={domain} stroke={SERIES.axis} label={{ value: "L, см", position: "insideBottomRight", offset: -14 }} />
            <YAxis
              type="number"
              scale="log"
              domain={yDomain}
              ticks={logTicks(yDomain)}
              allowDataOverflow
              width={64}
              stroke={SERIES.axis}
              tickFormatter={(v: number) => ms(v)}
            />
            <Tooltip
              cursor={false}
              content={({ active, payload }) => {
                const row = payload?.[0]?.payload as SpreadRow | undefined;
                if (!active || !row) return null;
                return (
                  <TooltipBox
                    title={`L = ${num(row.L, 1)} см`}
                    rows={[
                      {
                        color: row.method === "camera" ? SERIES.camera : SERIES.stopwatch,
                        label: `σ(T), ${row.method === "camera" ? "камера" : "секундомер"}`,
                        value: ms(row.sigma),
                      },
                    ]}
                  />
                );
              }}
            />
            <Scatter data={sw} dataKey="sigma" fill={SERIES.stopwatch} isAnimationActive={false} />
            <Scatter data={cam} dataKey="sigma" fill={SERIES.camera} shape="diamond" isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/** σ(T) секундомера против числа отсчитанных колебаний N; модель √2·σ/N. */
export function NDependenceChart({ analysis }: { analysis: Analysis }) {
  const { points, event_sigma } = analysis.n_dependence;
  const model = useMemo(() => {
    if (!event_sigma || points.length === 0) return [];
    const ns = points.map((p) => p.periods);
    return logspace(Math.min(...ns) / 1.3, Math.max(...ns) * 1.3, 40).map((n) => ({
      periods: n,
      model: (Math.SQRT2 * event_sigma) / n,
    }));
  }, [points, event_sigma]);
  const xDomain = logDomain(points.map((p) => p.periods), 1.3);
  const yDomain = logDomain(
    [...points.map((p) => p.std), ...model.map((m) => m.model)],
    1.15,
  );
  if (points.length < 2)
    return (
      <p className="muted small">
        Сделайте несколько ручных замеров с разным числом колебаний (например, 1, 5, 10, 20) для
        одной длины — график покажет, как ошибка падает с ростом N.
      </p>
    );

  return (
    <div>
      <div className="chart-legend">
        <LegendItem color={SERIES.stopwatch} label="Секундомер: σ(T) по повторам" />
        <LegendItem color={SERIES.theory} label={`Модель √2·σ/N, σ нажатия = ${ms(event_sigma)}`} kind="dashed" />
      </div>
      <div className="chart">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart margin={MARGIN}>
            <CartesianGrid stroke={SERIES.grid} vertical={false} />
            <XAxis
              dataKey="periods"
              type="number"
              scale="log"
              domain={xDomain}
              ticks={points.map((p) => p.periods)}
              allowDataOverflow
              stroke={SERIES.axis}
              tickFormatter={(v: number) => num(v, 0)}
              label={{ value: "N колебаний", position: "insideBottomRight", offset: -14 }}
            />
            <YAxis
              type="number"
              scale="log"
              domain={yDomain}
              ticks={logTicks(yDomain)}
              allowDataOverflow
              width={64}
              stroke={SERIES.axis}
              tickFormatter={(v: number) => ms(v)}
            />
            <Tooltip
              cursor={false}
              content={({ active, payload }) => {
                const row = payload?.[0]?.payload as { periods: number; std?: number; trials?: number } | undefined;
                if (!active || !row || row.std === undefined) return null;
                return (
                  <TooltipBox
                    title={`N = ${row.periods}`}
                    rows={[
                      { color: SERIES.stopwatch, label: "σ(T)", value: ms(row.std) },
                      { label: "Замеров", value: row.trials },
                    ]}
                  />
                );
              }}
            />
            <Line data={model} dataKey="model" stroke={SERIES.theory} strokeDasharray="5 4" strokeWidth={1.5} dot={false} isAnimationActive={false} />
            <Scatter data={points} dataKey="std" fill={SERIES.stopwatch} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
