import { DASH, num } from "../lib/format";
import { equivalentLength } from "../lib/physics";

interface Props {
  t0: number | null | undefined;
  g: number;
  /** Длина, измеренная линейкой (если серия привязана), — чтобы показать разницу. */
  measured?: number | null;
}

/**
 * Длина «по периоду» и её отличие от измеренной. Это не ошибка распознавания: у реального
 * маятника центр качания ниже точки, до которой мерили линейкой (центр шарика, ушко, перегиб
 * нити на крючке), поэтому эффективная длина обычно на 1–3 см больше.
 */
export function EquivalentLength({ t0, g, measured }: Props) {
  if (!t0) return <>{DASH}</>;
  const length = equivalentLength(t0, g);
  const delta = measured ? length - measured : null;
  return (
    <span title="Длина идеального маятника с таким периодом. Отличие от измеренной показывает, где на самом деле центр качания">
      {num(length, 1)}
      {delta !== null && (
        <span className="muted small">
          {" "}
          ({delta >= 0 ? "+" : "−"}
          {num(Math.abs(delta), 1)})
        </span>
      )}
    </span>
  );
}
