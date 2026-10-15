import { Link, NavLink, Outlet, useParams } from "react-router";

import { useExperiment } from "../api/hooks";
import { ErrorNotice, Loading } from "../components/Status";
import type { ExperimentContext } from "./experimentContext";

export function ExperimentLayout() {
  const experimentId = Number(useParams().experimentId);
  const query = useExperiment(experimentId);

  if (query.isPending) return <Loading />;
  if (query.isError) return <ErrorNotice error={query.error} />;
  const experiment = query.data;
  const base = `/experiments/${experiment.id}`;

  return (
    <>
      <div className="breadcrumbs no-print">
        <Link to="/">Эксперименты</Link> /
      </div>
      <div className="page-head">
        <div>
          <h1>
            {experiment.name}{" "}
            {experiment.is_demo && <span className="badge badge--accent">демо</span>}
          </h1>
          {experiment.notes && <p>{experiment.notes}</p>}
        </div>
      </div>
      <nav className="tabs no-print">
        <NavLink to={base} end>
          Измерения
        </NavLink>
        <NavLink to={`${base}/analysis`}>Анализ и выводы</NavLink>
        <NavLink to={`${base}/settings`}>Настройки</NavLink>
      </nav>
      <Outlet context={{ experiment } satisfies ExperimentContext} />
    </>
  );
}
