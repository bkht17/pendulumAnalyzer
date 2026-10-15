/** Домен логарифмической оси с запасом, чтобы крайние точки не обрезались. */
export function logDomain(values: number[], pad = 1.6): [number, number] {
  const positive = values.filter((v) => v > 0 && Number.isFinite(v));
  if (positive.length === 0) return [1e-3, 1];
  return [Math.min(...positive) / pad, Math.max(...positive) * pad];
}

/** Деления 1-2-5 в пределах домена: 0,01 · 0,02 · 0,05 · 0,1 … */
export function logTicks([lo, hi]: [number, number]): number[] {
  const ticks: number[] = [];
  for (let exp = Math.floor(Math.log10(lo)); exp <= Math.ceil(Math.log10(hi)); exp++) {
    for (const m of [1, 2, 5]) {
      const v = m * 10 ** exp;
      if (v >= lo && v <= hi) ticks.push(Number(v.toPrecision(3)));
    }
  }
  return ticks;
}
