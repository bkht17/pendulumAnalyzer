import type { ReactNode } from "react";

export function Loading({ label = "Загрузка…" }: { label?: string }) {
  return <div className="empty muted">{label}</div>;
}

export function ErrorNotice({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : String(error);
  return <div className="notice notice--critical">{message}</div>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}
