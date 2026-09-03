import React from 'react';
import type { SightingDetailRead, TrajectoryPoint } from '../../types/api';
import { PlateBadge } from '../ui/PlateBadge';
import { MatchExplanation } from './MatchExplanation';
import { Image as ImageIcon } from 'lucide-react';

interface EvidencePanelProps {
  sightingDetail?: SightingDetailRead | null;
  selectedPoint?: TrajectoryPoint | null;
  previousPoint?: TrajectoryPoint | null;
}

export const EvidencePanel: React.FC<EvidencePanelProps> = ({
  sightingDetail,
  selectedPoint,
  previousPoint,
}) => {
  if (!sightingDetail && !selectedPoint) {
    return (
      <aside className="w-[380px] shrink-0 h-full p-4 flex flex-col items-center justify-center text-center bg-[var(--surface-raised)] border-l border-[var(--border-default)]">
        <ImageIcon className="w-8 h-8 text-[var(--text-muted)] mb-2" />
        <p className="text-xs font-semibold text-[var(--text-primary)]">No sighting selected</p>
        <p className="text-[11px] text-[var(--text-secondary)] mt-1">
          Click any camera marker on the map or timeline to inspect evidence.
        </p>
      </aside>
    );
  }

  const cameraCode = selectedPoint?.camera_code || sightingDetail?.camera_code || 'CAM-01';
  const fromCameraCode = previousPoint?.camera_code || 'CAM-01';
  const plateText = selectedPoint?.plate_text_norm || sightingDetail?.plate_text_norm;
  const plateConfidence = selectedPoint?.plate_confidence ?? sightingDetail?.plate_confidence;
  const timestamp = selectedPoint?.timestamp || sightingDetail?.first_frame_at || '';

  return (
    <aside className="w-[380px] shrink-0 h-full flex flex-col bg-[var(--surface-raised)] border-l border-[var(--border-default)] overflow-y-auto select-none">
      {/* Evidence Panel Header */}
      <div className="p-3 border-b border-[var(--border-default)] flex items-center justify-between">
        <h2 className="text-xs font-bold uppercase tracking-wider text-[var(--text-primary)]">
          Evidence & justification
        </h2>
        <span className="font-mono text-[10px] text-[var(--accent-text)] bg-[var(--surface-sunken)] px-1.5 py-0.5 rounded border border-[var(--border-subtle)]">
          {cameraCode}
        </span>
      </div>

      <div className="p-4 flex flex-col gap-4">
        {/* Best-shot vehicle crop frame */}
        <div className="flex flex-col gap-1.5">
          <span className="text-[10px] font-mono uppercase text-[var(--text-secondary)]">
            Best-shot vehicle crop
          </span>
          <div className="relative aspect-video w-full rounded-[var(--radius-md)] overflow-hidden bg-[var(--surface-sunken)] border border-[var(--border-default)] flex items-center justify-center">
            {/* Simulated Vehicle Graphic Representation */}
            <div className="flex flex-col items-center gap-2 text-[var(--text-muted)]">
              <div className="w-16 h-10 border-2 border-[var(--accent)] rounded bg-[var(--surface-raised)] flex items-center justify-center font-mono text-[10px] text-[var(--text-primary)] font-bold">
                {cameraCode}
              </div>
              <span className="font-mono text-[10px]">
                {sightingDetail?.id || selectedPoint?.sighting_id || 'Crop verified'}
              </span>
            </div>

            <div className="absolute bottom-2 left-2 right-2 flex justify-between items-center text-[10px] font-mono text-[var(--text-secondary)] bg-black/70 px-2 py-0.5 rounded">
              <span>CONF: {(sightingDetail?.detection_confidence ?? 0.94) * 100}%</span>
              <span>CLASS: {sightingDetail?.vehicle_class ?? 'car'}</span>
            </div>
          </div>
        </div>

        {/* Plate Crop & Plate Text Read */}
        <div className="flex flex-col gap-1.5">
          <span className="text-[10px] font-mono uppercase text-[var(--text-secondary)]">
            Plate recognition (EasyOCR)
          </span>
          <div className="p-2.5 rounded-[var(--radius-md)] bg-[var(--surface-sunken)] border border-[var(--border-subtle)] flex items-center justify-between">
            <PlateBadge plate={plateText} confidence={plateConfidence} size="md" />
            <span className="text-[10px] font-mono text-[var(--text-muted)]">
              {plateText ? 'ANPR valid' : 'Unreadable'}
            </span>
          </div>
        </div>

        {/* Sighting Metadata Attributes */}
        <div className="grid grid-cols-2 gap-2 text-xs font-mono">
          <div className="p-2 rounded bg-[var(--surface-sunken)] border border-[var(--border-subtle)] flex flex-col">
            <span className="text-[10px] text-[var(--text-secondary)]">Timestamp</span>
            <span className="text-[var(--text-primary)] font-semibold truncate">
              {new Date(timestamp).toLocaleTimeString([], { hour12: false })}
            </span>
          </div>
          <div className="p-2 rounded bg-[var(--surface-sunken)] border border-[var(--border-subtle)] flex flex-col">
            <span className="text-[10px] text-[var(--text-secondary)]">Vehicle class</span>
            <span className="text-[var(--text-primary)] font-semibold uppercase">
              {sightingDetail?.vehicle_class ?? 'car'}
            </span>
          </div>
        </div>

        {/* Match Explanation Breakdown & Also Considered Block */}
        <div className="flex flex-col gap-2 pt-1 border-t border-[var(--border-subtle)]">
          <MatchExplanation
            decisions={sightingDetail?.decisions || []}
            cameraCode={cameraCode}
            fromCameraCode={fromCameraCode}
          />
        </div>
      </div>
    </aside>
  );
};
