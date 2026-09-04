import React, { useState, useRef, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Film, CheckCircle, AlertCircle, Loader2, Play, X, Plus } from 'lucide-react';
import { api } from '../lib/api';
import type { Camera } from '../types/api';
import { MOCK_CAMERAS } from '../mocks/mockData';
import { useUploadStore, type CameraJob } from '../stores/uploadStore';

const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

export const UploadPage: React.FC = () => {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [cameras, setCameras] = useState<Camera[]>(MOCK_CAMERAS);
  const [dragOver, setDragOver] = useState(false);
  const [nextCamera, setNextCamera] = useState<string>(MOCK_CAMERAS[0]?.code ?? 'CAM-01');
  const { jobs, addJob, removeJob, updateJob, clearAll } = useUploadStore();
  const [running, setRunning] = useState(false);

  useEffect(() => {
    api.getCameras().then(setCameras);
  }, []);

  const usedCodes = new Set(jobs.map(j => j.cameraCode));
  const availableCameras = cameras.filter(c => !usedCodes.has(c.code));

  useEffect(() => {
    if (availableCameras.length > 0 && usedCodes.has(nextCamera)) {
      setNextCamera(availableCameras[0].code);
    }
  }, [availableCameras, nextCamera, usedCodes]);

  const handleFiles = useCallback((files: FileList) => {
    const videoFiles = Array.from(files).filter(
      f => f.type.startsWith('video/') || f.name.match(/\.(mp4|avi|mkv|mov|webm)$/i)
    );
    for (const file of videoFiles) {
      const cam = availableCameras.find(c => c.code === nextCamera) ?? availableCameras[0];
      if (!cam) break;
      addJob(cam.code, file);
      const remaining = cameras.filter(c => !usedCodes.has(c.code) && c.code !== cam.code);
      if (remaining.length > 0) setNextCamera(remaining[0].code);
    }
  }, [nextCamera, availableCameras, cameras, usedCodes, addJob]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files.length > 0) handleFiles(e.dataTransfer.files);
  }, [handleFiles]);

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) handleFiles(e.target.files);
    if (fileInputRef.current) fileInputRef.current.value = '';
  }, [handleFiles]);

  const runAll = useCallback(async () => {
    setRunning(true);
    const queued = jobs.filter(j => j.status === 'queued');

    for (const job of queued) {
      updateJob(job.cameraCode, { status: 'uploading' });
      try {
        const formData = new FormData();
        formData.append('video', job.file);
        formData.append('camera_code', job.cameraCode);

        const res = await fetch(`${BASE}/upload/video`, { method: 'POST', body: formData });
        if (!res.ok) throw new Error(`Upload failed (${res.status})`);
        const result = await res.json();

        const videoUrl = `${BASE}/upload/serve/${result.video_filename}`;
        updateJob(job.cameraCode, {
          jobId: result.job_id,
          status: 'processing',
          videoUrl,
        });
      } catch (err) {
        console.error(`Upload failed for ${job.cameraCode}:`, err);
        updateJob(job.cameraCode, { status: 'failed' });
      }
    }
  }, [jobs, updateJob]);

  // Poll all processing jobs
  useEffect(() => {
    const processing = jobs.filter(j => j.status === 'processing' && j.jobId);
    if (processing.length === 0) {
      if (running && jobs.length > 0 && jobs.every(j => j.status === 'completed' || j.status === 'failed')) {
        setRunning(false);
      }
      return;
    }

    const interval = setInterval(async () => {
      for (const job of processing) {
        try {
          const res = await fetch(`${BASE}/upload/status/${job.jobId}`);
          if (!res.ok) continue;
          const data = await res.json();
          if (data.status === 'completed') updateJob(job.cameraCode, { status: 'completed' });
          else if (data.status === 'failed') updateJob(job.cameraCode, { status: 'failed' });
        } catch { /* keep polling */ }
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [jobs, running, updateJob]);

  const allDone = jobs.length > 0 && jobs.every(j => j.status === 'completed' || j.status === 'failed');
  const anyProcessing = jobs.some(j => j.status === 'processing' || j.status === 'uploading');

  return (
    <div className="flex-1 flex flex-col items-center justify-start p-6 overflow-y-auto bg-[var(--surface-base)]">
      <div className="w-full max-w-3xl">
        <h1 className="text-lg font-semibold text-[var(--text-primary)] mb-1">Upload videos</h1>
        <p className="text-xs text-[var(--text-secondary)] mb-6">
          Upload one video per camera. Assign each to a camera, then hit Run to process all simultaneously.
          Videos will play in the Live Wall while the pipeline runs.
        </p>

        {/* Queued videos list */}
        {jobs.length > 0 && (
          <div className="mb-4 space-y-2">
            {jobs.map(job => (
              <JobRow
                key={job.cameraCode}
                job={job}
                cameras={cameras}
                onRemove={() => removeJob(job.cameraCode)}
              />
            ))}
          </div>
        )}

        {/* Add more: camera selector + drop zone */}
        {availableCameras.length > 0 && !anyProcessing && !allDone && (
          <>
            <div className="mb-3 flex items-center gap-3">
              <label className="text-xs font-medium text-[var(--text-secondary)]">Next camera:</label>
              <select
                value={nextCamera}
                onChange={e => setNextCamera(e.target.value)}
                className="bg-[var(--surface-sunken)] border border-[var(--border-default)] rounded-[var(--radius-sm)] px-2 py-1 text-xs font-mono text-[var(--text-primary)]"
              >
                {availableCameras.map(c => (
                  <option key={c.code} value={c.code}>{c.code} — {c.name}</option>
                ))}
              </select>
            </div>

            <div
              onDrop={handleDrop}
              onDragOver={e => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onClick={() => fileInputRef.current?.click()}
              className={`
                border-2 border-dashed rounded-[var(--radius-lg)] p-8
                flex flex-col items-center justify-center gap-2
                cursor-pointer transition-colors mb-4
                ${dragOver
                  ? 'border-[var(--accent)] bg-[var(--accent-tint)]'
                  : 'border-[var(--border-default)] bg-[var(--surface-sunken)] hover:border-[var(--border-strong)]'
                }
              `}
            >
              <Plus className={`w-8 h-8 ${dragOver ? 'text-[var(--accent-text)]' : 'text-[var(--text-muted)]'}`} />
              <p className="text-sm text-[var(--text-primary)]">
                {dragOver ? 'Drop video here' : 'Add video'}
              </p>
              <p className="text-xs text-[var(--text-secondary)]">
                Drag and drop or click. Supports .mp4, .avi, .mkv, .mov
              </p>
              <input
                ref={fileInputRef}
                type="file"
                accept="video/*,.mp4,.avi,.mkv,.mov,.webm"
                multiple
                onChange={handleInputChange}
                className="hidden"
              />
            </div>
          </>
        )}

        {/* Action buttons */}
        <div className="flex gap-2">
          {jobs.length > 0 && jobs.some(j => j.status === 'queued') && (
            <button
              onClick={runAll}
              className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium bg-[var(--accent)] text-[var(--text-inverse)] rounded-[var(--radius-sm)] hover:bg-[var(--accent-hover)] cursor-pointer"
            >
              <Play className="w-4 h-4" />
              Run ({jobs.filter(j => j.status === 'queued').length} video{jobs.filter(j => j.status === 'queued').length !== 1 ? 's' : ''})
            </button>
          )}

          {allDone && (
            <>
              <button
                onClick={() => navigate('/')}
                className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium bg-[var(--accent)] text-[var(--text-inverse)] rounded-[var(--radius-sm)] hover:bg-[var(--accent-hover)] cursor-pointer"
              >
                View live wall
              </button>
              <button
                onClick={() => navigate('/sim')}
                className="px-4 py-2 text-sm font-medium bg-[var(--surface-sunken)] text-[var(--accent-text)] border border-[var(--accent)] rounded-[var(--radius-sm)] hover:bg-[var(--accent-tint)] cursor-pointer"
              >
                View simulation
              </button>
            </>
          )}

          {jobs.length > 0 && !anyProcessing && (
            <button
              onClick={clearAll}
              className="px-4 py-2 text-sm font-medium bg-[var(--surface-sunken)] text-[var(--text-secondary)] border border-[var(--border-default)] rounded-[var(--radius-sm)] hover:bg-[var(--surface-hover)] cursor-pointer"
            >
              Clear all
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

function JobRow({ job, cameras, onRemove }: { job: CameraJob; cameras: Camera[]; onRemove: () => void }) {
  const cam = cameras.find(c => c.code === job.cameraCode);
  const statusColors: Record<string, string> = {
    queued: 'var(--text-muted)',
    uploading: 'var(--status-ambiguous)',
    processing: 'var(--accent-text)',
    completed: 'var(--status-confirmed)',
    failed: 'var(--status-rejected)',
  };
  const color = statusColors[job.status] || 'var(--text-muted)';

  return (
    <div className="flex items-center gap-3 p-3 bg-[var(--surface-raised)] border border-[var(--border-default)] rounded-[var(--radius-md)]">
      <Film className="w-5 h-5 text-[var(--text-secondary)] shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-mono text-[var(--text-primary)] truncate">{job.file.name}</span>
          <span className="text-[11px] px-1.5 py-0.5 rounded-[var(--radius-sm)] font-mono"
            style={{ color, background: `color-mix(in srgb, ${color} 14%, transparent)` }}>
            {job.status}
          </span>
        </div>
        <span className="text-xs text-[var(--text-secondary)]">{job.cameraCode} — {cam?.name ?? ''}</span>
      </div>
      {(job.status === 'processing' || job.status === 'uploading') && (
        <Loader2 className="w-4 h-4 text-[var(--accent-text)] animate-spin shrink-0" />
      )}
      {job.status === 'completed' && <CheckCircle className="w-4 h-4 text-[var(--status-confirmed)] shrink-0" />}
      {job.status === 'failed' && <AlertCircle className="w-4 h-4 text-[var(--status-rejected)] shrink-0" />}
      {job.status === 'queued' && (
        <button onClick={onRemove} className="p-1 hover:bg-[var(--surface-hover)] rounded cursor-pointer">
          <X className="w-4 h-4 text-[var(--text-muted)]" />
        </button>
      )}
    </div>
  );
}
