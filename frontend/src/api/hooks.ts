import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";
import type {
  ExperimentDetail,
  ExperimentInput,
  SegmentPatch,
  SeriesInput,
  TrialInput,
  Video,
} from "./types";

export const keys = {
  experiments: ["experiments"] as const,
  experiment: (id: number) => ["experiment", id] as const,
  analysis: (id: number) => ["analysis", id] as const,
  video: (id: number) => ["video", id] as const,
  track: (id: number, processedAt: string | null) => ["track", id, processedAt] as const,
};

const isBusy = (v: Video) => v.status === "queued" || v.status === "processing";

export function useExperiments() {
  return useQuery({ queryKey: keys.experiments, queryFn: api.experiments });
}

export function useExperiment(id: number) {
  return useQuery({
    queryKey: keys.experiment(id),
    queryFn: () => api.experiment(id),
    // Пока какое-то видео обрабатывается, обновляем статусы.
    refetchInterval: (query) => {
      const data = query.state.data as ExperimentDetail | undefined;
      return data?.videos.some(isBusy) ? 1000 : false;
    },
  });
}

export function useAnalysis(id: number) {
  return useQuery({ queryKey: keys.analysis(id), queryFn: () => api.analysis(id) });
}

export function useVideo(id: number) {
  return useQuery({
    queryKey: keys.video(id),
    queryFn: () => api.video(id),
    refetchInterval: (query) => {
      const data = query.state.data as Video | undefined;
      return data && isBusy(data) ? 700 : false;
    },
  });
}

export function useTrack(video: Video | undefined) {
  return useQuery({
    queryKey: keys.track(video?.id ?? 0, video?.processed_at ?? null),
    queryFn: () => api.track(video!.id),
    enabled: !!video?.processed_at && !isBusy(video),
    retry: false,
  });
}

/** Любое изменение данных эксперимента делает устаревшими его детали, анализ и список. */
function useInvalidateExperiment() {
  const client = useQueryClient();
  return (experimentId: number) =>
    Promise.all([
      client.invalidateQueries({ queryKey: keys.experiment(experimentId) }),
      client.invalidateQueries({ queryKey: keys.analysis(experimentId) }),
      client.invalidateQueries({ queryKey: keys.experiments }),
    ]);
}

export function useCreateExperiment() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: ExperimentInput | "demo") =>
      input === "demo" ? api.createDemo() : api.createExperiment(input),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.experiments }),
  });
}

export function useUpdateExperiment(id: number) {
  const invalidate = useInvalidateExperiment();
  return useMutation({
    mutationFn: (patch: Partial<ExperimentInput>) => api.updateExperiment(id, patch),
    onSuccess: () => invalidate(id),
  });
}

export function useDeleteExperiment() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: api.deleteExperiment,
    onSuccess: () => client.invalidateQueries({ queryKey: keys.experiments }),
  });
}

export function useSeriesMutations(experimentId: number) {
  const invalidate = useInvalidateExperiment();
  const onSuccess = () => invalidate(experimentId);
  return {
    create: useMutation({
      mutationFn: (input: SeriesInput) => api.createSeries(experimentId, input),
      onSuccess,
    }),
    update: useMutation({
      mutationFn: ({ id, patch }: { id: number; patch: Partial<SeriesInput> }) =>
        api.updateSeries(id, patch),
      onSuccess,
    }),
    remove: useMutation({ mutationFn: api.deleteSeries, onSuccess }),
  };
}

export function useTrialMutations(experimentId: number) {
  const invalidate = useInvalidateExperiment();
  const onSuccess = () => invalidate(experimentId);
  return {
    create: useMutation({
      mutationFn: ({ seriesId, input }: { seriesId: number; input: TrialInput }) =>
        api.createTrial(seriesId, input),
      onSuccess,
    }),
    toggleExcluded: useMutation({
      mutationFn: ({ id, excluded }: { id: number; excluded: boolean }) =>
        api.updateTrial(id, { excluded }),
      onSuccess,
    }),
    remove: useMutation({ mutationFn: api.deleteTrial, onSuccess }),
  };
}

export function useSegmentMutations(experimentId: number, videoId: number) {
  const client = useQueryClient();
  const invalidate = useInvalidateExperiment();
  const onSuccess = async () => {
    await Promise.all([client.invalidateQueries({ queryKey: keys.video(videoId) }), invalidate(experimentId)]);
  };
  return {
    create: useMutation({
      mutationFn: (body: { t_start: number; t_end: number; series_id?: number | null }) =>
        api.createSegment(videoId, body),
      onSuccess,
    }),
    update: useMutation({
      mutationFn: ({ id, patch }: { id: number; patch: SegmentPatch }) => api.updateSegment(id, patch),
      onSuccess,
    }),
    remove: useMutation({ mutationFn: api.deleteSegment, onSuccess }),
    autoAssign: useMutation({ mutationFn: () => api.autoAssign(videoId), onSuccess }),
  };
}

export function useVideoMutations(experimentId: number) {
  const client = useQueryClient();
  const invalidate = useInvalidateExperiment();
  const onSuccess = async (video?: Video) => {
    if (video) client.setQueryData(keys.video(video.id), video);
    await invalidate(experimentId);
  };
  return {
    toggleExcluded: useMutation({
      mutationFn: ({ id, excluded }: { id: number; excluded: boolean }) =>
        api.updateVideo(id, { excluded }),
      onSuccess,
    }),
    remove: useMutation({ mutationFn: api.deleteVideo, onSuccess: () => onSuccess() }),
    track: useMutation({
      mutationFn: ({ id, params }: { id: number; params: Parameters<typeof api.startTracking>[1] }) =>
        api.startTracking(id, params),
      onSuccess,
    }),
    geometry: useMutation({
      mutationFn: ({ id, body }: { id: number; body: Parameters<typeof api.updateGeometry>[1] }) =>
        api.updateGeometry(id, body),
      onSuccess,
    }),
  };
}
