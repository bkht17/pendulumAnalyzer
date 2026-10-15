import { useOutletContext } from "react-router";

import type { ExperimentDetail } from "../api/types";

export interface ExperimentContext {
  experiment: ExperimentDetail;
}

export function useExperimentContext(): ExperimentContext {
  return useOutletContext<ExperimentContext>();
}
