import React from 'react';
import { useNavigate } from 'react-router-dom';
import type { LiveEventItem } from '../../hooks/usePollingSightings';
import { PlateBadge } from '../ui/PlateBadge';
import { StatusBadge } from '../ui/StatusBadge';

interface EventFeedRowProps {
  event: LiveEventItem;
}

export const EventFeedRow: React.FC<EventFeedRowProps> = ({ event }) => {
  const navigate = useNavigate();

  const handleClick = () => {
    if (event.vehicleId) {
      navigate(`/vehicles/${event.vehicleId}`);
    } else {
      navigate('/vehicles/veh-01');
    }
  };

  const formattedTime = new Date(event.timestamp).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });

  if (event.type === 'rejected') {
    return (
      <div
        onClick={handleClick}
        className="group relative p-2.5 rounded-[var(--radius-md)] bg-[var(--surface-raised)] border border-[var(--status-rejected)]/40 hover:border-[var(--status-rejected)] cursor-pointer select-none transition-none"
      >
        {/* Left accent bar for rejected event */}
        <div className="absolute left-0 top-0 bottom-0 w-1 bg-[var(--status-rejected)] rounded-l-[var(--radius-md)]" />

        <div className="pl-1.5 flex flex-col gap-1.5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <span className="font-mono text-xs font-bold text-[var(--status-rejected)]">
                GATE REJECTION
              </span>
              <span className="font-mono text-[10px] px-1 py-0.2 rounded bg-[var(--surface-sunken)] border border-[var(--border-subtle)] text-[var(--text-muted)]">
                {event.cameraCode}
              </span>
            </div>
            <span className="font-mono text-[11px] text-[var(--text-muted)]">{formattedTime}</span>
          </div>

          <div className="flex items-center gap-2 text-xs">
            <span className="font-mono font-semibold text-[var(--text-primary)]">
              {event.rejectionReason}
            </span>
            {event.vehicleRef && (
              <span className="font-mono text-[11px] text-[var(--text-secondary)]">
                against {event.vehicleRef}
              </span>
            )}
          </div>

          {/* Numbers breakdown - the competition differentiator */}
          {event.elapsedSeconds !== undefined && event.minTransitSeconds !== undefined && (
            <div className="text-[11px] font-mono text-[var(--text-secondary)] bg-[var(--surface-sunken)] px-2 py-1 rounded border border-[var(--border-subtle)] flex items-center justify-between">
              <span>Elapsed: {event.elapsedSeconds}s</span>
              <span className="text-[var(--status-rejected)]">
                Min feasible: {event.minTransitSeconds}s
              </span>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div
      onClick={handleClick}
      className="group relative p-2.5 rounded-[var(--radius-md)] bg-[var(--surface-raised)] border border-[var(--border-subtle)] hover:border-[var(--border-strong)] hover:bg-[var(--surface-hover)] cursor-pointer select-none transition-none"
    >
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs font-bold text-[var(--text-primary)]">
            {event.cameraCode}
          </span>
          {event.vehicleRef && (
            <span className="font-mono text-[11px] text-[var(--accent-text)] font-medium">
              {event.vehicleRef}
            </span>
          )}
        </div>
        <span className="font-mono text-[11px] text-[var(--text-muted)]">{formattedTime}</span>
      </div>

      <div className="flex items-center justify-between gap-2">
        <PlateBadge plate={event.plateText} size="sm" />
        {event.method && (
          <StatusBadge
            status={event.method === 'PLATE_EXACT' ? 'confirmed' : 'probable'}
            label={event.method}
          />
        )}
      </div>

      {event.score !== undefined && event.score !== null && (
        <div className="mt-1 flex items-center justify-end text-[10px] font-mono text-[var(--text-secondary)]">
          Score: {(event.score * 100).toFixed(0)}%
        </div>
      )}
    </div>
  );
};
