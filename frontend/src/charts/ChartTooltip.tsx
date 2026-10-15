import type { ReactNode } from "react";

export interface TooltipRow {
  color?: string;
  label: string;
  value: ReactNode;
}

export function TooltipBox({ title, rows }: { title?: ReactNode; rows: TooltipRow[] }) {
  return (
    <div className="chart-tooltip">
      {title && <div style={{ fontWeight: 600, marginBottom: 2 }}>{title}</div>}
      {rows.map((r) => (
        <div key={r.label}>
          {r.color && <span className="swatch" style={{ background: r.color }} />}
          <span className="secondary">{r.label}</span>
          <span style={{ marginLeft: "auto", paddingLeft: 12 }}>{r.value}</span>
        </div>
      ))}
    </div>
  );
}

export function LegendItem({ color, label, kind = "dot" }: { color: string; label: string; kind?: "dot" | "line" | "dashed" }) {
  return (
    <span>
      {kind === "dot" ? (
        <span className="swatch" style={{ background: color, borderRadius: "50%" }} />
      ) : (
        <span className={`legend-line ${kind === "dashed" ? "dashed" : ""}`} style={{ color }} />
      )}
      {label}
    </span>
  );
}
