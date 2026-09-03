import React from 'react';
import type { Camera } from '../../types/api';
import { cn } from '../../lib/cn';
import { Video } from 'lucide-react';

interface CameraTileProps {
  camera: Camera;
  isFlashing?: boolean;
  isSelected?: boolean;
  onClick?: () => void;
  recentTrackId?: number;
  recentPlate?: string | null;
}

export const CameraTile: React.FC<CameraTileProps> = ({
  camera,
  isFlashing = false,
  isSelected = false,
  onClick,
  recentTrackId,
  recentPlate,
}) => {
  return (
    <div
      onClick={onClick}
      className={cn(
        'relative aspect-video w-full rounded-[var(--radius-md)] overflow-hidden cursor-pointer select-none bg-[var(--surface-sunken)] border transition-none',
        isFlashing
          ? 'animate-tile-flash border-[var(--accent)]'
          : isSelected
          ? 'border-[var(--accent)] ring-1 ring-[var(--accent)]'
          : 'border-[var(--border-default)] hover:border-[var(--border-strong)]'
      )}
    >
      {/* Simulated Video Canvas / Stream Frame */}
      <div className="absolute inset-0 bg-[var(--surface-sunken)] flex items-center justify-center">
        {/* Subtle grid pattern to represent camera video matrix */}
        <div
          className="absolute inset-0 opacity-15"
          style={{
            backgroundImage:
              'linear-gradient(to right, var(--border-subtle) 1px, transparent 1px), linear-gradient(to bottom, var(--border-subtle) 1px, transparent 1px)',
            backgroundSize: '24px 24px',
          }}
        />

        {/* Camera stream placeholder representation */}
        <div className="relative flex flex-col items-center gap-2 text-[var(--text-muted)] opacity-60">
          <Video className="w-8 h-8 stroke-[1.2]" />
          <span className="font-mono text-xs tracking-wider">{camera.code} FEED</span>
        </div>

        {/* Simulated Detection Bounding Box Overlay per design.md §4 */}
        <div
          className="absolute border-2 border-[var(--detection-box)] pointer-events-none"
          style={{ top: '30%', left: '35%', width: '30%', height: '40%' }}
        >
          {/* Track ID Label */}
          <div className="absolute -top-5 left-0 bg-[var(--detection-label-bg)] px-1.5 py-0.5 text-[10px] font-mono text-[var(--text-primary)] rounded-[1px] border border-[var(--border-subtle)] whitespace-nowrap">
            ID:{recentTrackId || 42} • CAR 94%
          </div>

          {/* Plate Sub-box */}
          <div
            className="absolute bottom-2 left-1/4 w-1/2 h-5 border border-dashed border-[var(--detection-plate-box)] bg-black/40 flex items-center justify-center"
          >
            <span className="font-mono text-[9px] text-[var(--status-ambiguous)]">
              {recentPlate || 'OCR ACTIVE'}
            </span>
          </div>
        </div>
      </div>

      {/* 48px linear functional gradient overlay over lower edge per design.md §7 */}
      <div
        className="absolute inset-x-0 bottom-0 h-12 pointer-events-none"
        style={{
          background: 'linear-gradient(to top, rgba(14, 16, 18, 0.92) 0%, rgba(14, 16, 18, 0) 100%)',
        }}
      />

      {/* Camera metadata overlay */}
      <div className="absolute bottom-2 left-3 right-3 flex items-center justify-between pointer-events-none">
        <div className="flex flex-col">
          <div className="flex items-center gap-1.5">
            <span className="font-mono font-bold text-xs text-[var(--text-primary)]">
              {camera.code}
            </span>
            <span className="text-[11px] text-[var(--text-secondary)] truncate max-w-[140px]">
              {camera.name}
            </span>
          </div>
          {camera.location_label && (
            <span className="text-[10px] text-[var(--text-muted)] truncate max-w-[180px]">
              {camera.location_label}
            </span>
          )}
        </div>

        <div className="flex items-center gap-1 bg-[var(--surface-base)]/80 px-1.5 py-0.5 rounded text-[10px] font-mono border border-[var(--border-subtle)] text-[var(--accent-text)]">
          <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] animate-pulse" />
          <span>LIVE</span>
        </div>
      </div>
    </div>
  );
};
