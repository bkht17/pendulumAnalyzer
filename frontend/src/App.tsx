import { lazy, Suspense } from "react";
import { Link, NavLink, Route, Routes } from "react-router";

import { Loading } from "./components/Status";
import { ExperimentLayout } from "./pages/ExperimentLayout";
import { ExperimentsPage } from "./pages/ExperimentsPage";
import { MeasurementsPage } from "./pages/MeasurementsPage";
import { MethodPage } from "./pages/MethodPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { SeriesPage } from "./pages/SeriesPage";
import { SettingsPage } from "./pages/SettingsPage";

// Страницы с графиками тянут Recharts — грузим их отдельными чанками по требованию.
const AnalysisPage = lazy(() => import("./pages/AnalysisPage").then((m) => ({ default: m.AnalysisPage })));
const VideoPage = lazy(() => import("./pages/VideoPage").then((m) => ({ default: m.VideoPage })));

export function App() {
  return (
    <>
      <header className="app-header">
        <div className="app-header__inner">
          <Link to="/" className="brand">
            <img src="/favicon.svg" alt="" />
            <span className="brand__name">Секундомер против камеры</span>
          </Link>
          <nav className="nav">
            <NavLink to="/" end>
              Эксперименты
            </NavLink>
            <NavLink to="/method">Методика</NavLink>
          </nav>
        </div>
      </header>
      <main className="container">
        <Suspense fallback={<Loading />}>
        <Routes>
          <Route index element={<ExperimentsPage />} />
          <Route path="method" element={<MethodPage />} />
          <Route path="experiments/:experimentId" element={<ExperimentLayout />}>
            <Route index element={<MeasurementsPage />} />
            <Route path="analysis" element={<AnalysisPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="series/:seriesId" element={<SeriesPage />} />
            <Route path="videos/:videoId" element={<VideoPage />} />
          </Route>
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
        </Suspense>
      </main>
    </>
  );
}
