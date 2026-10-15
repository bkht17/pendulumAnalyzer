import type { ColorRange } from "../api/types";

interface Props {
  color: ColorRange;
  onChange: (color: ColorRange) => void;
}

const SLIDERS: { key: keyof ColorRange; label: string; max: number }[] = [
  { key: "h_min", label: "Оттенок от", max: 179 },
  { key: "h_max", label: "Оттенок до", max: 179 },
  { key: "s_min", label: "Насыщ. от", max: 255 },
  { key: "v_min", label: "Яркость от", max: 255 },
];

function hueSegments(c: ColorRange): { left: number; width: number }[] {
  const pct = (h: number) => (h / 180) * 100;
  if (c.h_min <= c.h_max) return [{ left: pct(c.h_min), width: pct(c.h_max - c.h_min + 1) }];
  // Диапазон «через ноль» (красный цвет): две части полосы.
  return [
    { left: pct(c.h_min), width: 100 - pct(c.h_min) },
    { left: 0, width: pct(c.h_max + 1) },
  ];
}

export function ColorControls({ color, onChange }: Props) {
  return (
    <div className="hsv-grid">
      <span />
      <div className="hue-strip" aria-hidden>
        {hueSegments(color).map((s, i) => (
          <span key={i} style={{ left: `${s.left}%`, width: `${s.width}%` }} />
        ))}
      </div>
      <span />
      {SLIDERS.map(({ key, label, max }) => (
        <label key={key} style={{ display: "contents" }}>
          <span className="secondary">{label}</span>
          <input
            type="range"
            min={0}
            max={max}
            value={color[key]}
            onChange={(e) => onChange({ ...color, [key]: Number(e.target.value) })}
          />
          <span className="nums">{color[key]}</span>
        </label>
      ))}
    </div>
  );
}
