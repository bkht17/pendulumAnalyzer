/** T/T₀ ≈ 1 + θ²/16 + 11θ⁴/3072 — то же, что backend/app/science/physics.py. */
export function amplitudeFactor(amplitudeDeg: number | null | undefined): number {
  if (!amplitudeDeg) return 1;
  const theta = (amplitudeDeg * Math.PI) / 180;
  return 1 + theta ** 2 / 16 + (11 * theta ** 4) / 3072;
}

/** Точки, равномерно распределённые по логарифмической шкале. */
export function logspace(from: number, to: number, count: number): number[] {
  const a = Math.log(from);
  const b = Math.log(to);
  return Array.from({ length: count }, (_, i) => Math.exp(a + ((b - a) * i) / (count - 1)));
}
