import { useCallback, useEffect, useRef, useState } from "react";

import { clock, num } from "../lib/format";
import { readLocal, writeLocal } from "../lib/storage";

interface Props {
  defaultPeriods: number;
  saving: boolean;
  onSave: (input: { periods: number; total_time_s: number; operator: string }) => void;
}

type State = { kind: "idle" } | { kind: "running"; start: number } | { kind: "stopped"; elapsed: number };

const isTyping = (target: EventTarget | null) =>
  target instanceof HTMLElement &&
  (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT");

/**
 * Встроенный секундомер. Момент нажатия берётся из event.timeStamp (время самого события
 * ввода), а не из времени обработки — так задержки браузера не добавляются к реакции человека.
 * Кнопка срабатывает на pointerdown, как настоящий секундомер, а не на отпускание.
 */
export function Stopwatch({ defaultPeriods, saving, onSave }: Props) {
  const [state, setState] = useState<State>({ kind: "idle" });
  const [now, setNow] = useState(0);
  const [periods, setPeriods] = useState(String(defaultPeriods));
  const [operator, setOperator] = useState(() => readLocal("operator", ""));
  const [autoSave, setAutoSave] = useState(() => readLocal("autosave", "0") === "1");
  const frame = useRef(0);

  const n = Number(periods);
  const periodsValid = Number.isInteger(n) && n >= 1 && n <= 500;

  useEffect(() => writeLocal("operator", operator), [operator]);
  useEffect(() => writeLocal("autosave", autoSave ? "1" : "0"), [autoSave]);

  useEffect(() => {
    if (state.kind !== "running") return;
    const tick = () => {
      setNow(performance.now());
      frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame.current);
  }, [state.kind]);

  // Ref нужен, чтобы обработчик нажатия видел актуальное состояние без побочных эффектов
  // внутри setState (StrictMode вызывает функции-обновители дважды).
  const stateRef = useRef(state);
  const update = useCallback((next: State) => {
    stateRef.current = next;
    setState(next);
  }, []);

  const save = useCallback(
    (elapsed: number) => {
      if (!periodsValid) return;
      onSave({ periods: n, total_time_s: Math.round(elapsed * 1000) / 1000, operator });
      update({ kind: "idle" });
    },
    [n, operator, onSave, periodsValid, update],
  );

  const toggle = useCallback(
    (timeStamp: number) => {
      const current = stateRef.current;
      if (current.kind === "running") {
        const elapsed = (timeStamp - current.start) / 1000;
        update({ kind: "stopped", elapsed });
        if (autoSave) save(elapsed);
      } else {
        setNow(timeStamp);
        update({ kind: "running", start: timeStamp });
      }
    },
    [autoSave, save, update],
  );

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (isTyping(event.target) || event.repeat) return;
      if (event.code === "Space") {
        event.preventDefault();
        toggle(event.timeStamp);
      } else if (event.key === "Enter" && state.kind === "stopped") {
        event.preventDefault();
        save(state.elapsed);
      } else if (event.key === "Escape") {
        update({ kind: "idle" });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggle, save, state, update]);

  const elapsed =
    state.kind === "running" ? Math.max(now - state.start, 0) / 1000 : state.kind === "stopped" ? state.elapsed : 0;

  return (
    <div className="stack">
      <div className="stopwatch">
        <div className={`stopwatch__display ${state.kind === "running" ? "running" : ""}`} aria-live="off">
          {clock(elapsed)}
        </div>
        {state.kind === "stopped" && periodsValid && (
          <div className="secondary">
            T = {num(elapsed, 3)} / {n} = <strong>{num(elapsed / n, 4)} с</strong>
          </div>
        )}
        <button
          type="button"
          className={`stopwatch__button ${state.kind === "running" ? "" : "primary"}`}
          onPointerDown={(e) => {
            if (e.button !== 0) return;
            e.preventDefault();
            toggle(e.timeStamp);
          }}
          onKeyDown={(e) => e.preventDefault()}
        >
          {state.kind === "running" ? "Стоп" : "Старт"}
        </button>
        {state.kind === "stopped" && (
          <div className="row">
            <button className="primary" disabled={!periodsValid || saving} onClick={() => save(state.elapsed)}>
              Сохранить <kbd>Enter</kbd>
            </button>
            <button onClick={() => update({ kind: "idle" })}>
              Сбросить <kbd>Esc</kbd>
            </button>
          </div>
        )}
        <div className="muted small">
          <kbd>Пробел</kbd> — старт/стоп. Включайте и выключайте в момент прохождения груза через
          нижнюю точку.
        </div>
      </div>
      <div className="form-row">
        <label className="field">
          Колебаний N
          <input
            inputMode="numeric"
            value={periods}
            onChange={(e) => setPeriods(e.target.value)}
            aria-invalid={!periodsValid}
          />
        </label>
        <label className="field">
          Кто измерял
          <input value={operator} onChange={(e) => setOperator(e.target.value)} placeholder="Имя" maxLength={100} />
        </label>
      </div>
      <label className="row small secondary">
        <input type="checkbox" checked={autoSave} onChange={(e) => setAutoSave(e.target.checked)} />
        Сохранять замер сразу после остановки
      </label>
    </div>
  );
}
