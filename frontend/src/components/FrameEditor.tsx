import { type PointerEvent, useEffect, useRef, useState } from "react";

import type { Point, Roi } from "../api/types";

export type Tool = "color" | "roi" | "pivot" | "scale";

interface Props {
  src: string;
  videoWidth: number;
  videoHeight: number;
  tool: Tool;
  roi: Roi | null;
  pivot: Point | null;
  scalePoints: Point[];
  detection: Point | null;
  mask: { png: string; roi: Roi } | null;
  onPoint: (point: Point) => void;
  onRoi: (roi: Roi | null) => void;
}

// Цвета разметки поверх видео — фиксированные и контрастные к любому кадру.
const ROI_COLOR = "#ffd400";
const MASK_RGB = [255, 0, 200] as const;
const DETECTION_COLOR = "#00e5ff";
const MARK_COLOR = "#ffffff";

/** Превращает чёрно-белую маску в полупрозрачную цветную заливку. */
async function tintMask(base64: string): Promise<HTMLCanvasElement> {
  const image = new Image();
  image.src = `data:image/png;base64,${base64}`;
  await image.decode();
  const canvas = document.createElement("canvas");
  canvas.width = image.width;
  canvas.height = image.height;
  const ctx = canvas.getContext("2d")!;
  ctx.drawImage(image, 0, 0);
  const data = ctx.getImageData(0, 0, canvas.width, canvas.height);
  const px = data.data;
  for (let i = 0; i < px.length; i += 4) {
    const on = px[i]! > 127;
    px[i] = MASK_RGB[0];
    px[i + 1] = MASK_RGB[1];
    px[i + 2] = MASK_RGB[2];
    px[i + 3] = on ? 150 : 0;
  }
  ctx.putImageData(data, 0, 0);
  return canvas;
}

function normalizeRoi(a: Point, b: Point): Roi {
  return {
    x: Math.round(Math.min(a.x, b.x)),
    y: Math.round(Math.min(a.y, b.y)),
    w: Math.round(Math.abs(a.x - b.x)),
    h: Math.round(Math.abs(a.y - b.y)),
  };
}

export function FrameEditor(props: Props) {
  const { src, videoWidth, videoHeight, tool, roi, pivot, scalePoints, detection, mask } = props;
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  // Окрашенная маска хранится вместе с исходником, чтобы не показать маску от старых настроек.
  const [tintedFor, setTintedFor] = useState<{ png: string; canvas: HTMLCanvasElement } | null>(null);
  const tinted = mask && tintedFor?.png === mask.png ? tintedFor.canvas : null;
  const [drag, setDrag] = useState<{ from: Point; to: Point } | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setSize({ w: entry.contentRect.width, h: entry.contentRect.height });
    });
    observer.observe(canvas);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!mask) return;
    let cancelled = false;
    tintMask(mask.png)
      .then((canvas) => !cancelled && setTintedFor({ png: mask.png, canvas }))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [mask]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || size.w === 0) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(size.w * dpr);
    canvas.height = Math.round(size.h * dpr);
    const ctx = canvas.getContext("2d")!;
    const k = size.w / videoWidth;
    ctx.setTransform(dpr * k, 0, 0, dpr * k, 0, 0);
    ctx.clearRect(0, 0, videoWidth, videoHeight);
    const line = 1.5 / k; // толщина линий в экранных пикселях

    if (tinted && mask) {
      ctx.drawImage(tinted, mask.roi.x, mask.roi.y, mask.roi.w, mask.roi.h);
    }

    const shownRoi = drag ? normalizeRoi(drag.from, drag.to) : roi;
    if (shownRoi) {
      ctx.fillStyle = "rgba(0,0,0,0.35)";
      ctx.beginPath();
      ctx.rect(0, 0, videoWidth, videoHeight);
      ctx.rect(shownRoi.x, shownRoi.y, shownRoi.w, shownRoi.h);
      ctx.fill("evenodd");
      ctx.strokeStyle = ROI_COLOR;
      ctx.lineWidth = line;
      ctx.strokeRect(shownRoi.x, shownRoi.y, shownRoi.w, shownRoi.h);
    }

    const cross = (p: Point, color: string, r: number) => {
      ctx.strokeStyle = "rgba(0,0,0,0.6)";
      ctx.lineWidth = line * 3;
      ctx.beginPath();
      ctx.moveTo(p.x - r, p.y);
      ctx.lineTo(p.x + r, p.y);
      ctx.moveTo(p.x, p.y - r);
      ctx.lineTo(p.x, p.y + r);
      ctx.stroke();
      ctx.strokeStyle = color;
      ctx.lineWidth = line;
      ctx.stroke();
    };

    if (pivot) {
      cross(pivot, MARK_COLOR, 10 / k);
      ctx.font = `${12 / k}px system-ui`;
      ctx.fillStyle = MARK_COLOR;
      // У верхнего края кадра подпись не помещается над точкой — ставим её ниже.
      const labelY = pivot.y < 24 / k ? pivot.y + 18 / k : pivot.y - 6 / k;
      ctx.fillText("подвес", pivot.x + 12 / k, labelY);
    }

    if (scalePoints.length > 0) {
      scalePoints.forEach((p) => cross(p, MARK_COLOR, 7 / k));
      if (scalePoints.length === 2) {
        const [a, b] = scalePoints as [Point, Point];
        ctx.setLineDash([6 / k, 4 / k]);
        ctx.strokeStyle = MARK_COLOR;
        ctx.lineWidth = line;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
        ctx.setLineDash([]);
      }
    }

    if (detection) {
      ctx.strokeStyle = DETECTION_COLOR;
      ctx.lineWidth = line * 1.5;
      ctx.beginPath();
      ctx.arc(detection.x, detection.y, 14 / k, 0, Math.PI * 2);
      ctx.stroke();
      cross(detection, DETECTION_COLOR, 6 / k);
    }
  }, [size, videoWidth, videoHeight, roi, drag, pivot, scalePoints, detection, tinted, mask]);

  const toVideo = (event: PointerEvent<HTMLCanvasElement>): Point => {
    const rect = event.currentTarget.getBoundingClientRect();
    return {
      x: Math.min(Math.max(((event.clientX - rect.left) / rect.width) * videoWidth, 0), videoWidth - 1),
      y: Math.min(Math.max(((event.clientY - rect.top) / rect.height) * videoHeight, 0), videoHeight - 1),
    };
  };

  return (
    <div className={`frame-editor tool-${tool}`} style={{ aspectRatio: `${videoWidth} / ${videoHeight}` }}>
      <img src={src} alt="Кадр видео" onLoad={() => setLoaded(true)} draggable={false} />
      {!loaded && (
        <div className="empty muted" style={{ position: "absolute", inset: 0 }}>
          Загрузка кадра…
        </div>
      )}
      <canvas
        ref={canvasRef}
        onPointerDown={(e) => {
          const p = toVideo(e);
          if (tool === "roi") {
            e.currentTarget.setPointerCapture(e.pointerId);
            setDrag({ from: p, to: p });
          } else {
            props.onPoint(p);
          }
        }}
        onPointerMove={(e) => drag && setDrag({ ...drag, to: toVideo(e) })}
        onPointerUp={() => {
          if (!drag) return;
          const next = normalizeRoi(drag.from, drag.to);
          setDrag(null);
          props.onRoi(next.w >= 8 && next.h >= 8 ? next : null);
        }}
      />
    </div>
  );
}
