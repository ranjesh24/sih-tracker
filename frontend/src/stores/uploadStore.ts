import { create } from 'zustand';

export interface CameraJob {
  cameraCode: string;
  file: File;
  jobId: string | null;
  status: 'queued' | 'uploading' | 'processing' | 'completed' | 'failed';
  videoUrl: string | null;
}

interface UploadStore {
  jobs: CameraJob[];
  addJob: (cameraCode: string, file: File) => void;
  removeJob: (cameraCode: string) => void;
  updateJob: (cameraCode: string, patch: Partial<CameraJob>) => void;
  clearAll: () => void;
  getVideoUrl: (cameraCode: string) => string | null;
}

export const useUploadStore = create<UploadStore>((set, get) => ({
  jobs: [],
  addJob: (cameraCode, file) =>
    set((s) => ({
      jobs: [
        ...s.jobs.filter((j) => j.cameraCode !== cameraCode),
        { cameraCode, file, jobId: null, status: 'queued', videoUrl: null },
      ],
    })),
  removeJob: (cameraCode) =>
    set((s) => ({ jobs: s.jobs.filter((j) => j.cameraCode !== cameraCode) })),
  updateJob: (cameraCode, patch) =>
    set((s) => ({
      jobs: s.jobs.map((j) => (j.cameraCode === cameraCode ? { ...j, ...patch } : j)),
    })),
  clearAll: () => set({ jobs: [] }),
  getVideoUrl: (cameraCode) => get().jobs.find((j) => j.cameraCode === cameraCode)?.videoUrl ?? null,
}));
