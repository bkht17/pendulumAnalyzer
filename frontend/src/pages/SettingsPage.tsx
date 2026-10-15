import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router";

import { useDeleteExperiment, useUpdateExperiment } from "../api/hooks";
import { ErrorNotice } from "../components/Status";
import { useExperimentContext } from "./experimentContext";

export function SettingsPage() {
  const { experiment } = useExperimentContext();
  const update = useUpdateExperiment(experiment.id);
  const remove = useDeleteExperiment();
  const navigate = useNavigate();
  const [name, setName] = useState(experiment.name);
  const [g, setG] = useState(String(experiment.g_reference));
  const [periods, setPeriods] = useState(String(experiment.main_periods));
  const [notes, setNotes] = useState(experiment.notes);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    update.mutate({
      name,
      g_reference: Number(g.replace(",", ".")),
      main_periods: Number(periods),
      notes,
    });
  };

  return (
    <div className="stack" style={{ maxWidth: 720 }}>
      <form className="card stack" onSubmit={submit}>
        <h2>Параметры эксперимента</h2>
        <label className="field">
          Название
          <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={200} />
        </label>
        <div className="form-row">
          <label className="field">
            Справочное g, м/с²
            <input inputMode="decimal" value={g} onChange={(e) => setG(e.target.value)} />
          </label>
          <label className="field">
            Колебаний в основном замере N
            <input inputMode="numeric" value={periods} onChange={(e) => setPeriods(e.target.value)} />
          </label>
        </div>
        <p className="muted small" style={{ margin: 0 }}>
          g зависит от широты и высоты: на экваторе ≈ 9,780, на полюсе ≈ 9,832 м/с². Для Алматы
          (43° с. ш., ~800 м) ≈ 9,802; для Астаны (51° с. ш.) ≈ 9,811.
        </p>
        <label className="field">
          Заметки (условия, оборудование)
          <textarea rows={4} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </label>
        <div className="row">
          <button className="primary" type="submit" disabled={update.isPending}>
            Сохранить
          </button>
          {update.isSuccess && <span className="badge badge--good">✓ сохранено</span>}
        </div>
        {update.isError && <ErrorNotice error={update.error} />}
      </form>

      <section className="card stack">
        <h3>Удаление</h3>
        <p className="secondary small">Удалятся все длины, замеры, видео и результаты обработки.</p>
        <div>
          <button
            className="danger"
            disabled={remove.isPending}
            onClick={() => {
              if (confirm(`Удалить эксперимент «${experiment.name}» безвозвратно?`))
                remove.mutate(experiment.id, { onSuccess: () => navigate("/") });
            }}
          >
            Удалить эксперимент
          </button>
        </div>
      </section>
    </div>
  );
}
