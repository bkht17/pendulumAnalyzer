import type { Video } from "../api/types";
import { num } from "../lib/format";

const LABELS: Record<Video["status"], string> = {
  uploaded: "нужна настройка",
  queued: "в очереди",
  processing: "обработка",
  done: "готово",
  failed: "ошибка",
};

export function VideoStatusBadge({ video }: { video: Video }) {
  if (video.excluded) return <span className="badge">исключено</span>;
  const tone =
    video.status === "done"
      ? "badge--good"
      : video.status === "failed"
        ? "badge--critical"
        : video.status === "uploaded"
          ? "badge--warn"
          : "badge--accent";
  const icon = video.status === "done" ? "✓" : video.status === "failed" ? "!" : "•";
  const progress =
    video.status === "processing" ? ` ${num(video.progress * 100, 0)} %` : "";
  return (
    <span className={`badge ${tone}`}>
      {icon} {LABELS[video.status]}
      {progress}
    </span>
  );
}
