"""Сводный анализ эксперимента: таблицы пп. 7–10 плана проекта и выводы.

Ключевая идея честного сравнения методов. И секундомер, и камера измеряют интервал
между двумя событиями, поэтому ошибка периода по N колебаниям равна √2·σ_события / N,
где σ_события — погрешность фиксации одного момента времени. Для секундомера она
оценивается по разбросу повторных замеров, для камеры — по остаткам регрессии моментов
прохождения равновесия. Сравнивая σ_события, мы сравниваем сами методы, а не число
колебаний, которое случайно уместилось в запись.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence

import numpy as np

from app.models import Experiment, Series, StopwatchTrial, VideoStatus
from app.schemas import (
    AnalysisOut,
    CameraStats,
    Estimate,
    LengthFit,
    MethodComparison,
    MethodTheory,
    NDependence,
    NDependencePoint,
    OverallComparison,
    RatioCheck,
    SegmentResultOut,
    SeriesAnalysis,
    StopwatchByN,
    StopwatchStats,
    SummaryOut,
    TheoryRow,
)
from app.science import physics
from app.science.stats import Summary, compare_variances, linear_fit, robust_outliers, summarize

RATIO_TARGET = 4.0
RATIO_TOLERANCE = 0.05
AGREEMENT_Z = 2.0


def _summary_out(s: Summary) -> SummaryOut:
    return SummaryOut(n=s.n, mean=s.mean, std=s.std, sem=s.sem, ci95=s.ci95)


def _pooled_std(groups: Iterable[tuple[float, int]]) -> tuple[float | None, int]:
    """Объединённое СКО по группам (σ, степени свободы)."""
    num = 0.0
    dof = 0
    for sigma, df in groups:
        if df > 0 and sigma is not None and math.isfinite(sigma):
            num += df * sigma**2
            dof += df
    return (math.sqrt(num / dof), dof) if dof else (None, 0)


def trial_outlier_flags(trials: Sequence[StopwatchTrial]) -> dict[int, bool]:
    flags: dict[int, bool] = {}
    by_n: dict[int, list[StopwatchTrial]] = defaultdict(list)
    for trial in trials:
        if not trial.excluded:
            by_n[trial.periods].append(trial)
    for group in by_n.values():
        for trial, flag in zip(group, robust_outliers([t.period_s for t in group]), strict=True):
            flags[trial.id] = flag
    return flags


def _active_trials(series: Series) -> list[StopwatchTrial]:
    return [t for t in series.trials if not t.excluded]


def _camera_results(series: Series) -> list[SegmentResultOut]:
    return [
        SegmentResultOut.model_validate(seg.result)
        for seg in series.segments
        if seg.result
        and not seg.excluded
        and not seg.video.excluded
        and seg.video.status is VideoStatus.DONE
    ]


def _weighted(values: list[float], ses: list[float | None]) -> Estimate:
    """Взвешенное среднее; погрешность — бо́льшая из внутренней и внешней оценок."""
    between = summarize(values)
    assert between is not None
    if all(se is not None and se > 0 for se in ses):
        weights = np.array([1 / se**2 for se in ses if se is not None])
        value = float(np.sum(weights * np.array(values)) / weights.sum())
        internal: float | None = float(1 / math.sqrt(weights.sum()))
    else:
        value, internal = between.mean, None
    candidates = [s for s in (internal, between.sem) if s is not None]
    return Estimate(value=value, sigma=max(candidates) if candidates else None)


def _main_trials(series: Series, main_periods: int) -> tuple[int, list[StopwatchTrial]]:
    trials = _active_trials(series)
    main = [t for t in trials if t.periods == main_periods]
    if main or not trials:
        return main_periods, main
    periods, _ = Counter(t.periods for t in trials).most_common(1)[0]
    return periods, [t for t in trials if t.periods == periods]


def _stopwatch_stats(series: Series, main_periods: int) -> StopwatchStats | None:
    periods, main = _main_trials(series, main_periods)
    summary = summarize([t.period_s for t in main])
    if summary is None:
        return None
    active = _active_trials(series)
    by_n: dict[int, list[float]] = defaultdict(list)
    for t in active:
        by_n[t.periods].append(t.period_s)
    return StopwatchStats(
        periods=periods,
        summary=_summary_out(summary),
        event_sigma=summary.std * periods / math.sqrt(2) if summary.std is not None else None,
        excluded=sum(t.excluded for t in series.trials),
        outliers=sum(trial_outlier_flags(series.trials).values()),
        by_periods=[
            StopwatchByN(periods=n, summary=_summary_out(s))
            for n in sorted(by_n)
            if (s := summarize(by_n[n])) is not None
        ],
    )


def _camera_stats(results: list[SegmentResultOut], compare_periods: int) -> CameraStats | None:
    between = summarize([r.period for r in results])
    if between is None:
        return None
    with_t0 = [r for r in results if r.t0 is not None]
    with_k = [r for r in results if r.amplitude_k is not None and r.amplitude_k_se]
    event_sigma, _ = _pooled_std(
        (r.event_sigma, r.crossings_count - 4) for r in results if r.event_sigma is not None
    )
    period_std, _ = _pooled_std(
        (r.period_std, len(r.period_values) - 1) for r in results if r.period_std is not None
    )
    amplitudes = [r.amplitude_mean_deg for r in results if r.amplitude_mean_deg is not None]
    lows = [r.theta_min_deg for r in results if r.theta_min_deg is not None]
    highs = [r.theta_max_deg for r in results if r.theta_max_deg is not None]
    return CameraStats(
        segments=len(results),
        period=_weighted([r.period for r in results], [r.period_se for r in results]),
        t0=(
            _weighted([r.t0 for r in with_t0 if r.t0], [r.t0_se for r in with_t0])
            if with_t0
            else None
        ),
        between_segments=_summary_out(between),
        event_sigma=event_sigma,
        equivalent_std=math.sqrt(2) * event_sigma / compare_periods if event_sigma else None,
        period_std=period_std,
        amplitude_deg=float(np.mean(amplitudes)) if amplitudes else None,
        amplitude_min_deg=min(lows) if lows else None,
        amplitude_max_deg=max(highs) if highs else None,
        amplitude_k=(
            _weighted(
                [r.amplitude_k for r in with_k if r.amplitude_k is not None],
                [r.amplitude_k_se for r in with_k],
            )
            if with_k
            else None
        ),
    )


def _method_theory(
    value: float,
    sigma: float | None,
    theory: TheoryRow,
    series: Series,
    t0: Estimate | None = None,
) -> MethodTheory:
    """С теорией сравнивается T₀ (если камера привела период к малой амплитуде) или
    средний период — с теорией, поправленной на среднюю амплитуду."""
    if t0 is not None:
        value, sigma, reference, t0_exp = t0.value, t0.sigma, theory.t0, t0.value
    else:
        reference = theory.t_corrected or theory.t0
        amp = theory.amplitude_deg
        t0_exp = value / physics.amplitude_factor(math.radians(amp)) if amp else value
    combined = math.hypot(sigma or 0.0, theory.t0_sigma)
    length_m = series.length_cm / 100
    return MethodTheory(
        compared="t0" if t0 is not None else "mean",
        deviation_pct=(value - reference) / reference * 100,
        z_score=abs(value - reference) / combined if combined > 0 else None,
        g=Estimate(
            value=physics.g_from_period(length_m, t0_exp),
            sigma=physics.g_from_period_sigma(
                length_m, series.length_sigma_cm / 100, t0_exp, sigma or 0.0
            ),
        ),
    )


def _comparison(
    stopwatch: StopwatchStats,
    main: list[StopwatchTrial],
    camera: CameraStats,
    camera_df: int,
) -> MethodComparison:
    sw = stopwatch.summary
    cam = camera.period
    diff_sigma = (
        math.hypot(sw.sem, cam.sigma) if sw.sem is not None and cam.sigma is not None else None
    )
    variance = (
        compare_variances(sw.std, sw.n - 1, camera.equivalent_std, camera_df)
        if sw.std is not None and camera.equivalent_std
        else None
    )
    errors = [t.period_s - cam.value for t in main]
    return MethodComparison(
        difference=sw.mean - cam.value,
        difference_sigma=diff_sigma,
        spread_ratio=variance.ratio if variance else None,
        f_statistic=variance.f_statistic if variance else None,
        p_value=variance.p_value if variance else None,
        stopwatch_rms_error=float(np.sqrt(np.mean(np.square(errors)))) if errors else None,
    )


def _analyze_series(series: Series, g: float, main_periods: int) -> SeriesAnalysis:
    stopwatch = _stopwatch_stats(series, main_periods)
    results = _camera_results(series)
    compare_periods = stopwatch.periods if stopwatch else main_periods
    camera = _camera_stats(results, compare_periods)

    length_m = series.length_cm / 100
    amplitude = (camera.amplitude_deg if camera else None) or series.amplitude_deg
    t0 = physics.period_small_angle(length_m, g)
    theory = TheoryRow(
        t0=t0,
        t0_sigma=physics.period_small_angle_sigma(length_m, series.length_sigma_cm / 100, g),
        amplitude_deg=amplitude,
        t_corrected=t0 * physics.amplitude_factor(math.radians(amplitude)) if amplitude else None,
    )

    comparison = None
    if stopwatch and camera:
        _, main = _main_trials(series, main_periods)
        camera_df = sum(max(r.crossings_count - 4, 0) for r in results)
        comparison = _comparison(stopwatch, main, camera, camera_df)

    return SeriesAnalysis(
        series_id=series.id,
        length_cm=series.length_cm,
        length_sigma_cm=series.length_sigma_cm,
        stopwatch=stopwatch,
        camera=camera,
        comparison=comparison,
        theory=theory,
        stopwatch_vs_theory=(
            _method_theory(stopwatch.summary.mean, stopwatch.summary.sem, theory, series)
            if stopwatch
            else None
        ),
        camera_vs_theory=(
            _method_theory(camera.period.value, camera.period.sigma, theory, series, camera.t0)
            if camera
            else None
        ),
    )


def _length_fit(points: list[tuple[float, float, float | None]]) -> LengthFit | None:
    """points: (L в м, T₀ в с, σT). Аппроксимация T² = k·L + b."""
    if len(points) < 2:
        return None
    lengths = [p[0] for p in points]
    squares = [p[1] ** 2 for p in points]
    sigmas = [2 * p[1] * p[2] if p[2] else math.nan for p in points]
    fit = linear_fit(lengths, squares, sigmas)
    if fit is None or fit.slope <= 0:
        return None
    k, b = fit.slope, fit.intercept
    g = 4 * math.pi**2 / k
    g_sigma = g * fit.slope_se / k if fit.slope_se is not None else None
    offset_sigma = (
        math.hypot(fit.intercept_se / k, b * fit.slope_se / k**2)
        if fit.intercept_se is not None and fit.slope_se is not None
        else None
    )
    return LengthFit(
        points=fit.n,
        slope=k,
        slope_se=fit.slope_se,
        intercept=b,
        intercept_se=fit.intercept_se,
        r2=fit.r2,
        g=Estimate(value=g, sigma=g_sigma),
        length_offset_cm=Estimate(
            value=b / k * 100, sigma=offset_sigma * 100 if offset_sigma is not None else None
        ),
    )


def _t0(row: SeriesAnalysis, value: float) -> float:
    amp = row.theory.amplitude_deg
    return value / physics.amplitude_factor(math.radians(amp)) if amp else value


def _ratio(a: Estimate | None, b: Estimate | None) -> Estimate | None:
    if a is None or b is None:
        return None
    r = b.value / a.value
    if a.sigma is None or b.sigma is None:
        return Estimate(value=r, sigma=None)
    return Estimate(value=r, sigma=r * math.hypot(a.sigma / a.value, b.sigma / b.value))


def _cam_estimate(row: SeriesAnalysis) -> Estimate | None:
    """Для отношений периодов камера отдаёт T₀: так разная амплитуда серий не мешает."""
    if row.camera is None:
        return None
    return row.camera.t0 or row.camera.period


def _sw_estimate(row: SeriesAnalysis) -> Estimate | None:
    if row.stopwatch is None:
        return None
    return Estimate(value=row.stopwatch.summary.mean, sigma=row.stopwatch.summary.sem)


def _ratios(rows: list[SeriesAnalysis]) -> list[RatioCheck]:
    checks = []
    for i, short in enumerate(rows):
        for long in rows[i + 1 :]:
            q = long.length_cm / short.length_cm
            if abs(q / RATIO_TARGET - 1) > RATIO_TOLERANCE:
                continue
            checks.append(
                RatioCheck(
                    short_cm=short.length_cm,
                    long_cm=long.length_cm,
                    expected=math.sqrt(q),
                    stopwatch=_ratio(_sw_estimate(short), _sw_estimate(long)),
                    camera=_ratio(_cam_estimate(short), _cam_estimate(long)),
                )
            )
    return checks


def _n_dependence(experiment: Experiment) -> tuple[NDependence, float | None, int]:
    per_n: dict[int, list[tuple[float, int]]] = defaultdict(list)
    counts: Counter[int] = Counter()
    event_groups: list[tuple[float, int]] = []
    for series in experiment.series:
        groups: dict[int, list[float]] = defaultdict(list)
        for t in _active_trials(series):
            groups[t.periods].append(t.period_s)
        for n, values in groups.items():
            s = summarize(values)
            if s is None or s.std is None:
                continue
            per_n[n].append((s.std, s.n - 1))
            counts[n] += s.n
            event_groups.append((s.std * n / math.sqrt(2), s.n - 1))
    points = []
    for n in sorted(per_n):
        std, _ = _pooled_std(per_n[n])
        if std is not None:
            points.append(NDependencePoint(periods=n, std=std, trials=counts[n]))
    event_sigma, dof = _pooled_std(event_groups)
    return NDependence(points=points, event_sigma=event_sigma), event_sigma, dof


def _overall(
    experiment: Experiment, stopwatch_event: float | None, stopwatch_df: int
) -> OverallComparison:
    camera_event, camera_df = _pooled_std(
        (r.event_sigma, r.crossings_count - 4)
        for series in experiment.series
        for r in _camera_results(series)
        if r.event_sigma is not None
    )
    variance = (
        compare_variances(stopwatch_event, stopwatch_df, camera_event, camera_df)
        if stopwatch_event and camera_event
        else None
    )
    return OverallComparison(
        stopwatch_event_sigma=stopwatch_event,
        camera_event_sigma=camera_event,
        ratio=variance.ratio if variance else None,
        p_value=variance.p_value if variance else None,
        stopwatch_df=stopwatch_df,
        camera_df=camera_df,
    )


def _weighted_k(values: list[Estimate]) -> Estimate:
    good = [v for v in values if v.sigma]
    if not good:
        return Estimate(value=float(np.mean([v.value for v in values])), sigma=None)
    w = np.array([1 / v.sigma**2 for v in good if v.sigma])
    value = float(np.sum(w * np.array([v.value for v in good])) / w.sum())
    return Estimate(value=value, sigma=float(1 / math.sqrt(w.sum())))


def _fmt(value: float, digits: int = 3) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def _pm(value: float, sigma: float | None) -> str:
    """Значение ± погрешность: погрешность — 2 значащие цифры, значение — с той же точностью."""
    if sigma is None or sigma <= 0 or not math.isfinite(sigma):
        return _fmt(value, 3)
    digits = min(max(1 - math.floor(math.log10(sigma)), 0), 6)
    return f"{_fmt(value, digits)} ± {_fmt(sigma, digits)}"


def _p_text(p: float) -> str:
    return "p < 0,001" if p < 0.001 else f"p = {_fmt(p)}"


def _conclusions(
    rows: list[SeriesAnalysis],
    overall: OverallComparison,
    fits: dict[str, LengthFit | None],
    ratios: list[RatioCheck],
    g_ref: float,
) -> list[str]:
    out: list[str] = []
    if not rows:
        return ["Добавьте хотя бы одну длину маятника и измерения, чтобы получить выводы."]

    sw, cam = overall.stopwatch_event_sigma, overall.camera_event_sigma
    if sw and cam and overall.ratio and overall.p_value is not None:
        verdict = (
            "Различие статистически значимо — гипотеза о меньшем разбросе видеометода "
            "подтверждается."
            if overall.p_value < 0.05
            else "Различие статистически не значимо — нужно больше повторных замеров."
        )
        out.append(
            f"Погрешность фиксации одного момента времени: секундомер ≈ {sw * 1000:.0f} мс, "
            f"камера ≈ {_fmt(cam * 1000, 1)} мс — в {overall.ratio:.0f} раз меньше "
            f"(F-тест, {_p_text(overall.p_value)}). {verdict}"
        )
    elif sw:
        out.append(
            f"Погрешность ручного запуска/остановки секундомера ≈ {sw * 1000:.0f} мс. "
            "Обработайте видео, чтобы сравнить методы."
        )
    elif cam:
        out.append(
            f"Погрешность фиксации момента по видео ≈ {_fmt(cam * 1000, 1)} мс. "
            "Добавьте ручные замеры (минимум 2 на длину), чтобы сравнить методы."
        )

    for label, key in (("камере", "camera_vs_theory"), ("секундомеру", "stopwatch_vs_theory")):
        theory_rows = [getattr(r, key) for r in rows if getattr(r, key) is not None]
        if not theory_rows:
            continue
        agree = sum(1 for t in theory_rows if t.z_score is not None and t.z_score < AGREEMENT_Z)
        mean_dev = float(np.mean([abs(t.deviation_pct) for t in theory_rows]))
        out.append(
            f"Сравнение с формулой T = 2π√(L/g) по {label}: среднее расхождение "
            f"{_fmt(mean_dev, 2)} %, в пределах погрешности (|z| < 2) — "
            f"{agree} из {len(theory_rows)} длин."
        )

    for label, fit in (("камеры", fits["camera"]), ("секундомера", fits["stopwatch"])):
        if fit is None or fit.points < 3:
            continue
        text = (
            f"По наклону графика T²(L) для {label}: g = {_pm(fit.g.value, fit.g.sigma)} м/с² "
            f"(справочное значение {_fmt(g_ref, 3)} м/с²)."
        )
        offset = fit.length_offset_cm
        if offset.sigma is not None and abs(offset.value) > 2 * offset.sigma:
            text += (
                f" Обнаружена систематическая добавка к длине {_pm(offset.value, offset.sigma)} см"
                " — вероятно, длина измерялась не до центра масс груза."
            )
        out.append(text)
        break  # достаточно лучшего доступного метода

    for check in ratios:
        est = check.camera or check.stopwatch
        if est is None:
            continue
        source = "камера" if check.camera else "секундомер"
        out.append(
            f"При увеличении длины с {check.short_cm:g} до {check.long_cm:g} см период вырос в "
            f"{_fmt(est.value, 3)} раза ({source}); теория предсказывает {_fmt(check.expected, 3)}."
        )

    ks = [r.camera.amplitude_k for r in rows if r.camera and r.camera.amplitude_k]
    if ks:
        k_est = _weighted_k(ks)
        if k_est.sigma:
            agree = abs(k_est.value - 1 / 16) < 2 * k_est.sigma
            out.append(
                f"Период растёт с амплитудой: по отдельным периодам T = T₀(1 + k·θ²), "
                f"k = {_pm(k_est.value, k_est.sigma)} (теория 1/16 = 0,0625) — "
                + ("согласуется с теорией." if agree else "отличается от теории больше 2σ.")
            )
    with_t0 = [r for r in rows if r.camera and r.camera.t0]
    if with_t0:
        out.append(
            "Камера приводит каждый период к малой амплитуде (T₀ = T / (1 + θ²/16 + …)), поэтому "
            "с формулой сравнивается T₀ — даже при больших углах отклонения."
        )
    big = [r for r in rows if r.theory.amplitude_deg and r.theory.amplitude_deg > 10]
    if big and not with_t0:
        out.append(
            "Амплитуда больше 10°: поправка к периоду превышает 0,2 % и сопоставима с "
            "точностью видеометода — уменьшите угол отклонения до 5–7°."
        )
    return out


def analyze_experiment(experiment: Experiment) -> AnalysisOut:
    g = experiment.g_reference
    rows = [_analyze_series(s, g, experiment.main_periods) for s in experiment.series]
    n_dep, sw_event, sw_df = _n_dependence(experiment)
    overall = _overall(experiment, sw_event, sw_df)

    fit_sw = _length_fit(
        [
            (r.length_cm / 100, _t0(r, r.stopwatch.summary.mean), r.stopwatch.summary.sem)
            for r in rows
            if r.stopwatch
        ]
    )
    fit_cam = _length_fit(
        [
            (
                r.length_cm / 100,
                r.camera.t0.value if r.camera.t0 else _t0(r, r.camera.period.value),
                r.camera.t0.sigma if r.camera.t0 else r.camera.period.sigma,
            )
            for r in rows
            if r.camera
        ]
    )
    ratios = _ratios(rows)
    return AnalysisOut(
        experiment_id=experiment.id,
        g_reference=g,
        main_periods=experiment.main_periods,
        series=rows,
        overall=overall,
        fit_stopwatch=fit_sw,
        fit_camera=fit_cam,
        ratios=ratios,
        n_dependence=n_dep,
        conclusions=_conclusions(
            rows, overall, {"camera": fit_cam, "stopwatch": fit_sw}, ratios, g
        ),
    )
