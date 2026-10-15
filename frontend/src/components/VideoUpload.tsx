import { type DragEvent, useRef, useState } from "react";

import { api } from "../api/client";
import type { Video } from "../api/types";
import { num } from "../lib/format";
import { ErrorNotice } from "./Status";

const ACCEPT = ".mp4,.mov,.m4v,.avi,.mkv,.webm,video/*";

interface Props {
  seriesId: number;
  onUploaded: (video: Video) => void;
}

export function VideoUpload({ seriesId, onUploaded }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<unknown>(null);

  const upload = async (file: File) => {
    setError(null);
    setProgress(0);
    try {
      const video = await api.uploadVideo(seriesId, file, setProgress);
      onUploaded(video);
    } catch (err) {
      setError(err);
    } finally {
      setProgress(null);
    }
  };

  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setOver(false);
    const file = event.dataTransfer.files[0];
    if (file) void upload(file);
  };

  return (
    <div className="stack">
      <div
        className={`dropzone ${over ? "over" : ""}`}
        role="button"
        tabIndex={0}
        onClick={() => progress === null && input.current?.click()}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={onDrop}
      >
        {progress === null ? (
          <>
            <strong>Перетащите видео сюда</strong> или нажмите, чтобы выбрать файл
            <div className="small muted">MP4, MOV, AVI, MKV, WEBM · лучше 60 кадр/с, 15–20 с</div>
          </>
        ) : (
          <div className="stack">
            <div>Загрузка… {num(progress * 100, 0)} %</div>
            <div className="progress">
              <div style={{ width: `${progress * 100}%` }} />
            </div>
          </div>
        )}
        <input
          ref={input}
          type="file"
          accept={ACCEPT}
          hidden
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = "";
            if (file) void upload(file);
          }}
        />
      </div>
      {error !== null && <ErrorNotice error={error} />}
    </div>
  );
}
