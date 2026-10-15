import { useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router";

import { keys, useVideoMutations } from "../api/hooks";
import type { ExperimentDetail } from "../api/types";
import { bytes, num } from "../lib/format";
import { VideoStatusBadge } from "./VideoStatusBadge";
import { VideoUpload } from "./VideoUpload";

interface Props {
  experiment: ExperimentDetail;
  /** Длина, со страницы которой загружают: ей достанется участок, если он в записи один. */
  seriesId?: number;
}

export function VideosCard({ experiment, seriesId }: Props) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const mutations = useVideoMutations(experiment.id);
  const base = `/experiments/${experiment.id}`;
  const videos = seriesId
    ? experiment.videos.filter((v) => v.preferred_series_id === seriesId || v.segments.some((s) => s.series_id === seriesId))
    : experiment.videos;

  return (
    <section className="card stack">
      <div className="card__title">
        <h3>Видеозаписи</h3>
        <span className="muted small">{experiment.videos.length}</span>
      </div>
      <p className="secondary small" style={{ margin: 0 }}>
        Можно загрузить одну длинную запись с несколькими сериями (разными длинами нити) — программа сама найдёт
        участки колебаний, а вы привяжете их к длинам.
      </p>
      <VideoUpload
        experimentId={experiment.id}
        seriesId={seriesId}
        onUploaded={(video) => {
          void client.invalidateQueries({ queryKey: keys.experiment(experiment.id) });
          navigate(`${base}/videos/${video.id}`);
        }}
      />
      {videos.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Файл</th>
                <th className="left">Статус</th>
                <th>Длительность</th>
                <th>Серий найдено</th>
                <th>Привязано</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {videos.map((v) => (
                <tr key={v.id} className={v.excluded ? "excluded" : undefined}>
                  <td>
                    <Link to={`${base}/videos/${v.id}`}>{v.original_name}</Link>
                    <div className="muted small">
                      {v.width}×{v.height} · {num(v.fps_nominal, 0)} кадр/с · {bytes(v.size_bytes)}
                    </div>
                  </td>
                  <td className="left">
                    <VideoStatusBadge video={v} />
                  </td>
                  <td>{num(v.duration_s, 1)} с</td>
                  <td>{v.segments.length}</td>
                  <td>{v.segments.filter((s) => s.series_id).length}</td>
                  <td className="actions">
                    <div className="row" style={{ gap: 4, flexWrap: "nowrap" }}>
                      <Link className="button small" to={`${base}/videos/${v.id}`}>
                        {v.status === "uploaded" ? "Настроить" : "Открыть"}
                      </Link>
                      <button
                        className="small ghost danger icon"
                        title="Удалить видео"
                        aria-label="Удалить видео"
                        onClick={() => confirm(`Удалить ${v.original_name}?`) && mutations.remove.mutate(v.id)}
                      >
                        ✕
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
