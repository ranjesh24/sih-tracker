import React from 'react';
import { AlertTriangle, PowerOff } from 'lucide-react';

export type ConnectionStatus = 'live' | 'polling' | 'offline';

interface ConnectionIndicatorProps {
  status: ConnectionStatus;
  cameraCount?: number;
  indexSize?: number;
  lastUpdated?: Date | null;
}

export const ConnectionIndicator: React.FC<ConnectionIndicatorProps> = ({
  status,
  cameraCount = 4,
  indexSize = 154,
  lastUpdated,
}) => {
  return (
    <div className="flex items-center gap-3 text-xs">
      <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-[var(--surface-sunken)] border border-[var(--border-subtle)]">
        {status === 'live' || status === 'polling' ? (
          <>
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--accent)] opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-[var(--accent)]"></span>
            </span>
            <span className="font-mono text-[var(--text-primary)] font-medium">Batch live</span>
          </>
        ) : status === 'offline' ? (
          <>
            <PowerOff className="w-3 h-3 text-[var(--status-offline)]" />
            <span className="font-mono text-[var(--text-muted)]">Offline</span>
          </>
        ) : (
          <>
            <AlertTriangle className="w-3 h-3 text-[var(--status-ambiguous)]" />
            <span className="font-mono text-[var(--status-ambiguous)]">Connecting</span>
          </>
        )}
      </div>

      <div className="hidden sm:flex items-center gap-2 text-[var(--text-secondary)] font-mono">
        <span>{cameraCount} cameras</span>
        <span className="text-[var(--border-strong)]">/</span>
        <span>{indexSize} vectors</span>
        {lastUpdated && (
          <>
            <span className="text-[var(--border-strong)]">/</span>
            <span className="text-[var(--text-muted)]">
              {lastUpdated.toLocaleTimeString([], { hour12: false })}
            </span>
          </>
        )}
      </div>
    </div>
  );
};
