import React from 'react';
import { NavLink } from 'react-router-dom';
import { Video, MapPin, FileSearch, Upload } from 'lucide-react';
import { ConnectionIndicator, type ConnectionStatus } from './ConnectionIndicator';
import { cn } from '../../lib/cn';

interface TopBarProps {
  status: ConnectionStatus;
  cameraCount?: number;
  indexSize?: number;
  lastUpdated?: Date | null;
  activeVehicleId?: string;
  onSelectVehicle?: (vehicleId: string) => void;
  vehicles?: { id: string; display_ref: string; canonical_plate?: string | null }[];
}

export const TopBar: React.FC<TopBarProps> = ({
  status,
  cameraCount = 0,
  indexSize = 154,
  lastUpdated,
  activeVehicleId = '',
  onSelectVehicle,
  vehicles = [],
}) => {
  return (
    <header className="h-12 w-full bg-[var(--surface-raised)] border-b border-[var(--border-default)] px-4 flex items-center justify-between z-30 shrink-0 select-none">
      {/* Brand & System Code */}
      <div className="flex items-center gap-6">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-[var(--radius-sm)] bg-[var(--accent)] flex items-center justify-center text-[var(--text-inverse)] font-bold text-xs">
            M
          </div>
          <div className="flex flex-col">
            <div className="flex items-center gap-1.5">
              <span className="font-semibold tracking-tight text-sm text-[var(--text-primary)]">
                MAARG
              </span>
              <span className="text-[10px] font-mono px-1 py-0.2 rounded bg-[var(--surface-sunken)] border border-[var(--border-subtle)] text-[var(--text-secondary)]">
                SIH26127
              </span>
            </div>
          </div>
        </div>

        {/* 3 Main Navigation Tabs */}
        <nav className="flex items-center gap-1">
          <NavLink
            to="/"
            end
            className={({ isActive }) =>
              cn(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-[var(--radius-sm)] text-xs font-medium transition-none',
                isActive
                  ? 'bg-[var(--surface-hover)] text-[var(--text-primary)] border-b-2 border-[var(--accent)]'
                  : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-hover)]'
              )
            }
          >
            <Video className="w-3.5 h-3.5" />
            <span>Live wall</span>
          </NavLink>

          <NavLink
            to={`/vehicles/${activeVehicleId}`}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-[var(--radius-sm)] text-xs font-medium transition-none',
                isActive
                  ? 'bg-[var(--surface-hover)] text-[var(--text-primary)] border-b-2 border-[var(--accent)]'
                  : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-hover)]'
              )
            }
          >
            <MapPin className="w-3.5 h-3.5" />
            <span>Trajectory map</span>
          </NavLink>

          <NavLink
            to={`/evidence/${activeVehicleId}`}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-[var(--radius-sm)] text-xs font-medium transition-none',
                isActive
                  ? 'bg-[var(--surface-hover)] text-[var(--text-primary)] border-b-2 border-[var(--accent)]'
                  : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-hover)]'
              )
            }
          >
            <FileSearch className="w-3.5 h-3.5" />
            <span>Evidence panel</span>
          </NavLink>

          <NavLink
            to="/upload"
            className={({ isActive }) =>
              cn(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-[var(--radius-sm)] text-xs font-medium transition-none',
                isActive
                  ? 'bg-[var(--surface-hover)] text-[var(--text-primary)] border-b-2 border-[var(--accent)]'
                  : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-hover)]'
              )
            }
          >
            <Upload className="w-3.5 h-3.5" />
            <span>Upload</span>
          </NavLink>
        </nav>
      </div>

      {/* Right side status & vehicle selector */}
      <div className="flex items-center gap-4">
        {/* Options come from the database. They were previously three
            hardcoded ids that existed nowhere, so every lookup 404'd and the
            UI silently fell back to fixture data with no crops. */}
        {onSelectVehicle && vehicles.length > 0 && (
          <div className="hidden md:flex items-center gap-1.5 text-xs">
            <span className="text-[var(--text-secondary)]">Vehicle:</span>
            <select
              value={activeVehicleId}
              onChange={(e) => onSelectVehicle(e.target.value)}
              className="bg-[var(--surface-sunken)] border border-[var(--border-default)] rounded-[var(--radius-sm)] px-2 py-1 text-xs font-mono text-[var(--text-primary)] focus:outline-none focus:border-[var(--accent)]"
            >
              {vehicles.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.display_ref}{v.canonical_plate ? ` — ${v.canonical_plate}` : ' — no plate'}
                </option>
              ))}
            </select>
          </div>
        )}

        <ConnectionIndicator
          status={status}
          cameraCount={cameraCount}
          indexSize={indexSize}
          lastUpdated={lastUpdated}
        />
      </div>
    </header>
  );
};
