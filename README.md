# Stopwatch vs Camera

A web app for a school research project. It measures the period of a simple pendulum in two
ways, by hand with a stopwatch and automatically from video (OpenCV tracking). It then compares
the two methods with each other and with the formula T = 2π√(L/g).

The user interface is in Russian. Labels quoted below are given in Russian with an English
translation.

Features:

- **Built-in stopwatch** (Space starts and stops, Enter saves), plus manual entry of times from
  an external stopwatch. Trials where the oscillation count was probably lost are flagged
  automatically.
- **Marker-free tracking.** The bob is found by background subtraction, so a plain steel ball
  works. A second method tracks a coloured marker by HSV colour. The detection mask is shown
  over the frame before you start, and tracking runs in the background with a progress bar.
- **Long recordings with several runs.** The app finds stretches of free oscillation without
  hands in the frame on its own, for example four string lengths in one 5-minute video. Each
  run is linked to its own length, and its bounds can be adjusted by hand.
- **Measured lengths stay in control.** Lengths can be edited inline, a list such as `60 40 20`
  can be added in one go, and the «Привязать по периоду» ("Match by period") button links runs
  to the closest length. The «L по периоду» ("L from period") column shows the length of an
  ideal pendulum with the measured period. It is an estimate, not a measurement: the
  difference from the ruler length shows where the real centre of oscillation is (usually
  1–3 cm lower).
- **Sub-frame period from video.** Timestamps are taken where the bob passes the equilibrium
  position and are refined by a phase fit over the whole central part of each half-swing. A
  regression runs through them, and tracking glitches are rejected. Variable-frame-rate videos
  are handled correctly.
- **Amplitude correction.** The pivot point and string length come from the arc of the
  trajectory, with no clicks needed. Every single period is reduced to small amplitude,
  T₀ = T / (1 + θ²/16 + …), and the 1/16 coefficient is checked by a fit. This makes runs swung
  at 20–40° comparable with the formula too.
- **Analysis following items 7–10 of the project plan**: comparison of the methods' spread
  (F-test), comparison with theory including the amplitude correction, g from the slope of
  T²(L) with an estimate of the unaccounted length offset, the period ratio check for lengths
  in a 1:4 ratio, and the dependence of stopwatch error on N. Conclusions are written
  automatically.
- CSV export of the tables (opens directly in Excel with a Russian locale), print or PDF, and
  download of the bob trajectory.
- **Demo mode**: synthetic pendulum videos with a known period, to walk through the whole
  pipeline before filming anything.

## Quick start

Requires Python ≥ 3.11 (tested on 3.14) and Node.js ≥ 20 (tested on 24).

```bash
make install
```

Development uses two terminals; the UI is at http://localhost:5173.

```bash
make dev-backend
```

```bash
make dev-frontend
```

A single app (API plus the built UI) at http://localhost:8000:

```bash
make run
```

Then click **«Создать демо-эксперимент»** ("Create demo experiment") on the home page. API
documentation (Swagger) is at http://localhost:8000/docs.

Data (SQLite and uploaded videos) is stored in `data/`. Set `PENDULUM_DATA_DIR` to move it.
Other settings: `PENDULUM_MAX_UPLOAD_MB` (default 1024) and `PENDULUM_TRACKING_WORKERS`
(default 2).

## Running an experiment

1. Create an experiment. In «Настройки» ("Settings"), set g for your city and the main number
   of oscillations N (default 10).
2. Add the lengths you measured with a ruler, for example `60 40 20`. Measure to the **centre**
   of the bob.
3. On a length's page, start recording on the phone and take readings with the built-in
   stopwatch at the same time. Press when the bob passes the lowest point. Take 10 or more
   readings per length.
4. Upload the video. One long recording with all the runs is fine. The «Движение» ("Motion")
   method needs no marker. Optionally draw a box around the swing area (cover the arc of every
   run) and mark the scale from a ruler in the frame. Start tracking.
5. Click «Привязать по периоду» ("Match by period") or pick a length for each run by hand. If
   you change the scale or the pivot point later, click «Применить подвес и масштаб» ("Apply
   pivot and scale"); this recalculates from the saved trajectory without tracking again.
6. The «Анализ и выводы» ("Analysis and conclusions") tab has the tables, charts and
   ready-made wording for the report.

The full method and its reasoning are in the app itself, in the «Методика» ("Method")
section.

## Architecture

```
backend/                     FastAPI + SQLAlchemy 2 + SQLite
  app/science/               pure functions with no web code: easy to test and to show at the defence
    tracking.py              OpenCV: background (median/percentile/bob masked out) or HSV mask → blob → centre
    pipeline.py              two passes: tracking → run detection → re-tracking each run with a clean background
    segments.py              finding stretches of free oscillation in a long recording
    geometry.py              pivot point and string length from the trajectory arc (robust circle fit)
    periods.py               equilibrium crossings, phase refinement, regression with drift, outliers
    physics.py               formulas, amplitude correction, T₀ from single periods, uncertainties
    stats.py                 summary statistics, weighted least squares, F-test, MAD outliers
    synthetic.py             pendulum video generator (nonlinear equation, known period)
  app/services/              experiment analysis, background tracking queue, run matching, demo data
  app/api/                   REST: experiments, lengths, trials, videos (upload, frame, preview, tracking), runs
  tests/                     pytest: science, tracking on synthetic video, end-to-end API
frontend/                    React 19 + TypeScript + Vite 8 + TanStack Query + Recharts
  src/pages/                 experiments, measurements, length, video, analysis, settings, method
  src/components/            stopwatch, frame editor (canvas), trials table, run table, upload
  src/charts/                tracking and analysis charts (palette checked for colour blindness)
```

Key decisions:

- **Background processing uses a thread pool**, not Celery and Redis. OpenCV releases the GIL,
  and a separate broker is overkill for a local single-user app. Status and progress live in
  the database. After a server restart, unfinished jobs are marked as interrupted.
- **Frame times come from the container** (`CAP_PROP_POS_MSEC`). OpenCV 5 was checked to
  return exact timestamps for variable-frame-rate video as well.
- **Two tracking passes.** The bob spoils a median background if it is held still before
  release, or if the amplitude is smaller than its diameter. So every detected run is tracked
  again with a background built from that run's frames only, and for small amplitudes with the
  bob masked out as well.
- **Runs are matched to lengths by period with a margin.** Measured lengths are usually
  2–3 cm shorter than the effective pendulum length, so lengths closer than about 6 % are
  left for the user to assign.
- **The database schema is versioned** (`PRAGMA user_version`). An incompatible old database
  and its videos folder are not deleted but moved to `*.bak`.
- **The methods are compared fairly** through σ, the uncertainty of timing a single event. For
  both methods the error of a period over N oscillations is √2·σ/N, so the length of the video
  does not affect the conclusion.
- **Tables are created with `create_all`, without Alembic.** That is enough for a local
  SQLite database. If the schema starts changing often, migrations are worth adding.
- **TypeScript 6.0, not 7**: typescript-eslint supports only versions below 6.1 for now.

## Tests and checks

```bash
make test
```

```bash
make lint
```

The backend tests generate pendulum videos with a known period, including a case where the
bob is held for 9 seconds before release. They check that tracking (with and without a marker)
is off by less than 1 px, that the period matches theory within 0.03 %, that run detection
finds releases between hand movements and pushes, that the pivot and string length are
recovered from the arc, that runs from a real recording match their measured lengths, and that
the full demo experiment recovers g and the built-in 0.8 cm length error.

## Check on a real recording

`IMG_9685.MOV`: iPhone, 30 fps, HEVC, 5.5 min, a steel ball without a marker, string lengths
60, 40 and 20 cm plus one shorter run. With no setup, the app found 6 runs and estimated the
single-event timing error at 0.6–1.5 ms. A person with a stopwatch is typically at 30–60 ms.
Two independent releases at 60 cm gave mean periods of 1.59217 and 1.59229 s; after reduction
to small amplitude, their T₀ values agree within the uncertainty. «Привязать по периоду»
("Match by period") linked all five runs to the right lengths. The effective length came out
2.4–3.2 cm longer than the ruler length (the centre of the ball, the eyelet and the bend of the
string over the hook).
