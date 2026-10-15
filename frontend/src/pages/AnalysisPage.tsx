import { api } from "../api/client";
import { useAnalysis } from "../api/hooks";
import type { Analysis, LengthFit, MethodTheory } from "../api/types";
import {
  NDependenceChart,
  PeriodSquaredChart,
  PeriodVsLengthChart,
  SpreadChart,
} from "../charts/AnalysisCharts";
import { SERIES } from "../charts/series";
import { Kpi } from "../components/Kpi";
import { Empty, ErrorNotice, Loading } from "../components/Status";
import { DASH, ms, num, pct, pm, pValue } from "../lib/format";
import { useExperimentContext } from "./experimentContext";

function Agreement({ theory }: { theory: MethodTheory | null }) {
  if (!theory || theory.z_score === null) return <>{DASH}</>;
  return theory.z_score < 2 ? (
    <span className="badge badge--good">✓ |z| = {num(theory.z_score, 1)}</span>
  ) : (
    <span className="badge badge--warn">! |z| = {num(theory.z_score, 1)}</span>
  );
}

function MethodDot({ method }: { method: "camera" | "stopwatch" }) {
  return <span className="swatch" style={{ background: method === "camera" ? SERIES.camera : SERIES.stopwatch }} />;
}

function ComparisonTable({ analysis }: { analysis: Analysis }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>L, см</th>
            <th>
              <MethodDot method="stopwatch" /> T секундомер, с
            </th>
            <th>Разброс σ, мс</th>
            <th>Замеров</th>
            <th>
              <MethodDot method="camera" /> T камера, с
            </th>
            <th>T₀ камера (малые колеб.), с</th>
            <th>Разброс при том же N, мс</th>
            <th>Участков видео</th>
            <th>Разница, мс</th>
            <th>Разброс меньше в</th>
            <th>p (F-тест)</th>
            <th>Ошибка ручного замера (СКО), мс</th>
          </tr>
        </thead>
        <tbody>
          {analysis.series.map((s) => (
            <tr key={s.series_id}>
              <td>{num(s.length_cm, 1)}</td>
              <td>{s.stopwatch ? pm(s.stopwatch.summary.mean, s.stopwatch.summary.sem) : DASH}</td>
              <td>{ms(s.stopwatch?.summary.std)}</td>
              <td>
                {s.stopwatch ? `${s.stopwatch.summary.n} × ${s.stopwatch.periods}` : DASH}
                {s.stopwatch?.outliers ? " " : null}
                {s.stopwatch?.outliers ? (
                  <span className="badge badge--warn" title="Есть подозрительные замеры — проверьте их на странице длины">
                    ! выброс: {s.stopwatch.outliers}
                  </span>
                ) : null}
              </td>
              <td>{s.camera ? pm(s.camera.period.value, s.camera.period.sigma, 5) : DASH}</td>
              <td>{s.camera?.t0 ? pm(s.camera.t0.value, s.camera.t0.sigma, 5) : DASH}</td>
              <td>{ms(s.camera?.equivalent_std)}</td>
              <td>{s.camera?.segments ?? DASH}</td>
              <td>
                {s.comparison
                  ? `${num(s.comparison.difference * 1000, 1)}${s.comparison.difference_sigma ? ` ± ${num(s.comparison.difference_sigma * 1000, 1)}` : ""}`
                  : DASH}
              </td>
              <td>{s.comparison?.spread_ratio ? `${num(s.comparison.spread_ratio, 0)}×` : DASH}</td>
              <td>{pValue(s.comparison?.p_value)}</td>
              <td>{ms(s.comparison?.stopwatch_rms_error)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TheoryTable({ analysis }: { analysis: Analysis }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>L, см</th>
            <th>T теория, с</th>
            <th>Амплитуда</th>
            <th>T теория с поправкой, с</th>
            <th>
              <MethodDot method="stopwatch" /> Откл. секундомера
            </th>
            <th>Согласие</th>
            <th>
              <MethodDot method="camera" /> Откл. камеры
            </th>
            <th>Согласие</th>
            <th>g по секундомеру, м/с²</th>
            <th>g по камере, м/с²</th>
          </tr>
        </thead>
        <tbody>
          {analysis.series.map((s) => (
            <tr key={s.series_id}>
              <td>{num(s.length_cm, 1)}</td>
              <td>{pm(s.theory.t0, s.theory.t0_sigma)}</td>
              <td>{s.theory.amplitude_deg ? `${num(s.theory.amplitude_deg, 1)}°` : DASH}</td>
              <td>{num(s.theory.t_corrected, 4)}</td>
              <td>{pct(s.stopwatch_vs_theory?.deviation_pct, 2, true)}</td>
              <td>
                <Agreement theory={s.stopwatch_vs_theory} />
              </td>
              <td title={s.camera_vs_theory?.compared === "t0" ? "T₀ камеры против T₀ теории" : "средний T против теории с поправкой"}>
                {pct(s.camera_vs_theory?.deviation_pct, 3, true)}
                {s.camera_vs_theory?.compared === "t0" && <span className="muted small"> (T₀)</span>}
              </td>
              <td>
                <Agreement theory={s.camera_vs_theory} />
              </td>
              <td>{s.stopwatch_vs_theory ? pm(s.stopwatch_vs_theory.g.value, s.stopwatch_vs_theory.g.sigma) : DASH}</td>
              <td>{s.camera_vs_theory ? pm(s.camera_vs_theory.g.value, s.camera_vs_theory.g.sigma) : DASH}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function FitRow({ label, method, fit, gRef }: { label: string; method: "camera" | "stopwatch"; fit: LengthFit | null; gRef: number }) {
  if (!fit) return null;
  const dev = ((fit.g.value - gRef) / gRef) * 100;
  return (
    <tr>
      <td className="left">
        <MethodDot method={method} /> {label}
      </td>
      <td>{fit.points}</td>
      <td>{pm(fit.slope, fit.slope_se)}</td>
      <td>{pm(fit.g.value, fit.g.sigma)}</td>
      <td>{pct(dev, 2, true)}</td>
      <td>{pm(fit.length_offset_cm.value, fit.length_offset_cm.sigma, 2)}</td>
      <td>{num(fit.r2, 5)}</td>
    </tr>
  );
}

export function AnalysisPage() {
  const { experiment } = useExperimentContext();
  const query = useAnalysis(experiment.id);

  if (query.isPending) return <Loading />;
  if (query.isError) return <ErrorNotice error={query.error} />;
  const analysis = query.data;
  if (analysis.series.length === 0) return <Empty>Добавьте длины и измерения — здесь появятся таблицы, графики и выводы.</Empty>;
  const { overall } = analysis;
  const bestFit = analysis.fit_camera ?? analysis.fit_stopwatch;

  return (
    <div className="stack">
      <div className="row no-print">
        <a className="button" href={api.exportUrl(experiment.id)} download>
          Скачать таблицу (CSV для Excel)
        </a>
        <button onClick={() => window.print()}>Печать / PDF</button>
        <span className="spacer" />
        <span className="muted small">
          g справочное = {num(analysis.g_reference, 3)} м/с² · основное N = {analysis.main_periods}
        </span>
      </div>

      <section className="card">
        <h2>Выводы</h2>
        <ul className="conclusions">
          {analysis.conclusions.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
      </section>

      <div className="kpis">
        <Kpi
          label={
            <>
              <MethodDot method="stopwatch" /> Ошибка нажатия секундомера
            </>
          }
          value={ms(overall.stopwatch_event_sigma)}
          hint={`по ${overall.stopwatch_df} степеням свободы`}
        />
        <Kpi
          label={
            <>
              <MethodDot method="camera" /> Ошибка момента по видео
            </>
          }
          value={ms(overall.camera_event_sigma)}
          hint={`по ${overall.camera_df} степеням свободы`}
        />
        <Kpi
          label="Камера точнее в"
          value={overall.ratio ? `${num(overall.ratio, 0)} раз` : DASH}
          hint={overall.p_value !== null ? `F-тест: p ${overall.p_value < 0.001 ? "< 0,001" : `= ${num(overall.p_value, 3)}`}` : "нужны оба метода"}
        />
        <Kpi
          label="g по графику T²(L)"
          value={bestFit ? `${pm(bestFit.g.value, bestFit.g.sigma)}` : DASH}
          hint={bestFit ? `м/с², ${analysis.fit_camera ? "камера" : "секундомер"}` : "нужно хотя бы 2 длины"}
        />
      </div>

      <section className="card">
        <h2>Сравнение двух методов (п. 7)</h2>
        <p className="secondary small">
          «Разброс при том же N» — каким был бы разброс камеры, если бы она, как и секундомер,
          измеряла {analysis.main_periods} колебаний: √2·σ<sub>момента</sub>/N. Так методы
          сравниваются честно, независимо от длины записи.
        </p>
        <ComparisonTable analysis={analysis} />
      </section>

      <div className="grid-2">
        <section className="card">
          <h3>Разброс одного замера</h3>
          <SpreadChart analysis={analysis} />
        </section>
        <section className="card">
          <h3>Ошибка секундомера от числа колебаний</h3>
          <NDependenceChart analysis={analysis} />
        </section>
      </div>

      <section className="card">
        <h2>Сравнение с теорией T = 2π√(L/g) (п. 8)</h2>
        <p className="secondary small">
          Для камеры с теорией сравнивается T₀ — период, пересчитанный к малой амплитуде по каждому отдельному
          периоду; для секундомера — средний период против теории с поправкой на среднюю амплитуду.
          |z| = |ΔT| / σ — согласие в пределах погрешности при |z| &lt; 2. Обычно его ограничивает
          не таймер, а точность длины: ошибка 0,5 см при L = 20 см даёт 1,25 % в периоде.
        </p>
        <TheoryTable analysis={analysis} />
      </section>

      <div className="grid-2">
        <section className="card">
          <h3>Период от длины</h3>
          <PeriodVsLengthChart analysis={analysis} />
        </section>
        <section className="card">
          <h3>Линеаризация: T² от L</h3>
          <PeriodSquaredChart analysis={analysis} />
        </section>
      </div>

      <section className="card">
        <h2>Ускорение свободного падения (п. 10)</h2>
        <p className="secondary small">
          Аппроксимация T² = k·L + b методом наименьших квадратов: g = 4π²/k. Отрезок b/k — длина,
          которую «не добрали» при измерении (обычно расстояние до центра масс груза). Это сильнее,
          чем считать g по каждой длине отдельно: систематическая ошибка длины не искажает наклон.
        </p>
        {analysis.fit_camera || analysis.fit_stopwatch ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th className="left">Метод</th>
                  <th>Точек</th>
                  <th>Наклон k, с²/м</th>
                  <th>g, м/с²</th>
                  <th>От справочного</th>
                  <th>Добавка к длине b/k, см</th>
                  <th>R²</th>
                </tr>
              </thead>
              <tbody>
                <FitRow label="Камера" method="camera" fit={analysis.fit_camera} gRef={analysis.g_reference} />
                <FitRow label="Секундомер" method="stopwatch" fit={analysis.fit_stopwatch} gRef={analysis.g_reference} />
              </tbody>
            </table>
          </div>
        ) : (
          <p className="muted small">Нужно минимум две длины с измерениями.</p>
        )}
      </section>

      <section className="card">
        <h2>Проверка T ∝ √L: длины, отличающиеся в 4 раза (п. 9)</h2>
        {analysis.ratios.length === 0 ? (
          <p className="muted small">
            Нет пар длин с отношением ≈ 4 (например, 20 и 80 см, 25 и 100 см).
          </p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Длины, см</th>
                  <th>Ожидаемое отношение √(L₂/L₁)</th>
                  <th>
                    <MethodDot method="stopwatch" /> Секундомер
                  </th>
                  <th>
                    <MethodDot method="camera" /> Камера
                  </th>
                </tr>
              </thead>
              <tbody>
                {analysis.ratios.map((r) => (
                  <tr key={`${r.short_cm}-${r.long_cm}`}>
                    <td>
                      {num(r.short_cm, 0)} и {num(r.long_cm, 0)}
                    </td>
                    <td>{num(r.expected, 3)}</td>
                    <td>{r.stopwatch ? pm(r.stopwatch.value, r.stopwatch.sigma) : DASH}</td>
                    <td>{r.camera ? pm(r.camera.value, r.camera.sigma) : DASH}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
