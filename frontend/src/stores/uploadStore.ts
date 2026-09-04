import { create } from 'zustand';

export interface CameraJob {
  cameraCode: string;
  file: File;
  jobId: string | null;
  status: 'queued' | 'uploading' | 'processing' | 'completed' | 'failed';
  videoUrl: string | null;
}

interface UploadStore {
  /** Identifies this upload session. Sent with every video so the backend
   *  records batch membership as a fact rather than guessing it from upload
   *  timestamps — the guess merged separate sessions and left stale cameras
   *  rendering on the live wall. */
  batchId: string;
  startNewBatch: () => string;
  jobs: CameraJob[];
  addJob: (cameraCode: string, file: File) => void;
  removeJob: (cameraCode: string) => void;
  updateJob: (cameraCode: string, patch: Partial<CameraJob>) => void;
  clearAll: () => void;
  getVideoUrl: (cameraCode: string) => string | null;
}

function newBatchId(): string {
  return globalThis.crypto?.randomUUID
    ? globalThis.crypto.randomUUID()
    : `batch-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export const useUploadStore = create<UploadStore>((set, get) => ({
  batchId: newBatchId(),
  startNewBatch: () => {
    const batchId = newBatchId();
    set({ batchId, jobs: [] });
    return batchId;
  },
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
