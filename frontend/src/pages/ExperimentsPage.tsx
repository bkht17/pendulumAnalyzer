import { type FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router";

import { useCreateExperiment, useExperiments } from "../api/hooks";
import { Empty, ErrorNotice, Loading } from "../components/Status";
import { num, plural } from "../lib/format";

export function ExperimentsPage() {
  const experiments = useExperiments();
  const create = useCreateExperiment();
  const navigate = useNavigate();
  const [name, setName] = useState("");

  const open = (id: number) => navigate(`/experiments/${id}`);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim()) return;
    create.mutate({ name: name.trim() }, { onSuccess: (e) => open(e.id) });
  };

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>Эксперименты</h1>
          <p>
            Сравнение точности измерения периода маятника: ручной секундомер против
            видеотрекинга.
          </p>
        </div>
      </div>

      <div className="grid-2">
        <form className="card stack" onSubmit={submit}>
          <h2>Новый эксперимент</h2>
          <label className="field">
            Название
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Например: «Основная серия, 14 октября»"
              maxLength={200}
            />
          </label>
          <div className="row">
            <button className="primary" type="submit" disabled={!name.trim() || create.isPending}>
              Создать
            </button>
          </div>
        </form>

        <div className="card stack">
          <h2>Демо-режим</h2>
          <p className="secondary">
            Шесть синтетических видео маятника с известным периодом и смоделированные ручные
            замеры. Удобно, чтобы увидеть весь путь обработки до настоящей съёмки.
          </p>
          <div className="row">
            <button
              type="button"
              onClick={() => create.mutate("demo", { onSuccess: (e) => open(e.id) })}
              disabled={create.isPending}
            >
              Создать демо-эксперимент
            </button>
          </div>
        </div>
      </div>

      {create.isError && <ErrorNotice error={create.error} />}

      {experiments.isPending && <Loading />}
      {experiments.isError && <ErrorNotice error={experiments.error} />}
      {experiments.data?.length === 0 && (
        <Empty>Пока нет ни одного эксперимента — создайте первый или запустите демо.</Empty>
      )}
      {experiments.data && experiments.data.length > 0 && (
        <div className="grid-cards">
          {experiments.data.map((e) => (
            <Link key={e.id} to={`/experiments/${e.id}`} className="card card--link">
              <div className="card__title">
                <h3>{e.name}</h3>
                {e.is_demo && <span className="badge badge--accent">демо</span>}
              </div>
              <div className="secondary small">
                {e.series_count} {plural(e.series_count, "длина", "длины", "длин")} ·{" "}
                {e.trials_count} {plural(e.trials_count, "замер", "замера", "замеров")} ·{" "}
                {e.videos_count} видео
              </div>
              <div className="muted small">
                g = {num(e.g_reference, 3)} м/с² · N = {e.main_periods} ·{" "}
                {new Date(e.created_at).toLocaleDateString("ru-RU")}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
