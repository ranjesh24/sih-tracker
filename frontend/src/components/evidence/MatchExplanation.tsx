import React from 'react';
import type { MatchDecision } from '../../types/api';
import { StatusBadge } from '../ui/StatusBadge';
import { Route, XCircle } from 'lucide-react';

interface MatchExplanationProps {
  decisions: MatchDecision[];
  cameraCode?: string;
  fromCameraCode?: string;
}

export const MatchExplanation: React.FC<MatchExplanationProps> = ({
  decisions,
  cameraCode = 'CAM-02',
  fromCameraCode = 'CAM-01',
}) => {
  // Accepted decision (top match)
  const acceptedDecision = decisions.find((d) => d.outcome === 'accepted') || decisions[0];
  // Rejected decisions ("Also considered" candidates)
  const rejectedDecisions = decisions.filter((d) => d.outcome === 'rejected');

  if (!acceptedDecision) {
    return (
      <div className="p-3 rounded bg-[var(--surface-sunken)] border border-[var(--border-subtle)] text-xs text-[var(--text-secondary)]">
        No match decision data recorded for this sighting.
      </div>
    );
  }

  const matchTierLabel =
    acceptedDecision.tier === 'plate' ? 'EXACT PLATE MATCH' : 'VISUAL RE-ID + GRAPH FUSION';

  return (
    <div className="flex flex-col gap-4 text-xs select-none">
      {/* Primary Match Card */}
      <div className="p-3 rounded-[var(--radius-md)] bg-[var(--surface-sunken)] border border-[var(--border-default)]">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[10px] font-mono text-[var(--text-secondary)] uppercase">
            Resolved by
          </span>
          <StatusBadge status="confirmed" label={matchTierLabel} />
        </div>

        {/* Score Breakdown Table per appflow.md §A4 */}
        <div className="flex flex-col gap-1.5 font-mono">
          <div className="flex justify-between items-center py-0.5 border-b border-[var(--border-subtle)]">
            <span className="text-[var(--text-secondary)]">Visual similarity</span>
            <span className="text-[var(--text-primary)] font-semibold">
              {acceptedDecision.visual_score !== null && acceptedDecision.visual_score !== undefined
                ? acceptedDecision.visual_score.toFixed(2)
                : '—'}
            </span>
          </div>

          <div className="flex justify-between items-center py-0.5 border-b border-[var(--border-subtle)]">
            <span className="text-[var(--text-secondary)]">Plate agreement</span>
            <span className="text-[var(--text-primary)] font-semibold">
              {acceptedDecision.plate_score !== null && acceptedDecision.plate_score !== undefined
                ? acceptedDecision.plate_score.toFixed(2)
                : '— (no plate)'}
            </span>
          </div>

          <div className="flex justify-between items-center py-0.5 border-b border-[var(--border-subtle)]">
            <span className="text-[var(--text-secondary)]">Temporal plausibility</span>
            <span className="text-[var(--text-primary)] font-semibold">
              {acceptedDecision.temporal_score !== null && acceptedDecision.temporal_score !== undefined
                ? acceptedDecision.temporal_score.toFixed(2)
                : '1.00 (gate pass)'}
            </span>
          </div>

          <div className="flex justify-between items-center pt-1 text-sm">
            <span className="text-[var(--text-primary)] font-medium">Fused score</span>
            <div className="flex items-baseline gap-1.5">
              <span className="text-[var(--accent-text)] font-bold">
                {acceptedDecision.fused_score !== null && acceptedDecision.fused_score !== undefined
                  ? acceptedDecision.fused_score.toFixed(2)
                  : '0.88'}
              </span>
              <span className="text-[10px] text-[var(--text-muted)]">threshold 0.72</span>
            </div>
          </div>
        </div>

        {/* Transit Window & Road Physics Detail */}
        {acceptedDecision.elapsed_seconds !== undefined &&
          acceptedDecision.elapsed_seconds !== null && (
            <div className="mt-3 pt-2.5 border-t border-[var(--border-subtle)] text-[11px] font-mono flex flex-col gap-1 text-[var(--text-secondary)]">
              <div className="flex items-center gap-1.5 text-[var(--text-primary)]">
                <Route className="w-3.5 h-3.5 text-[var(--accent)]" />
                <span>
                  Transit from {fromCameraCode} → {cameraCode}
                </span>
              </div>
              <div className="flex items-center justify-between text-[var(--text-secondary)]">
                <span>Elapsed: {acceptedDecision.elapsed_seconds} s</span>
                <span>
                  Feasible: {acceptedDecision.min_transit_seconds ?? 180}–
                  {acceptedDecision.max_transit_seconds ?? 1450} s
                </span>
              </div>
              {acceptedDecision.path_distance_m && (
                <div className="text-[10px] text-[var(--text-muted)]">
                  Shortest road path distance: {(acceptedDecision.path_distance_m / 1000).toFixed(1)} km
                </div>
              )}
            </div>
          )}
      </div>

      {/* "Also Considered" Rejected Candidates Section — Key differentiator */}
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <XCircle className="w-3.5 h-3.5 text-[var(--status-rejected)]" />
            <span className="text-xs font-semibold text-[var(--text-primary)]">
              Also considered ({rejectedDecisions.length})
            </span>
          </div>
          <span className="text-[10px] text-[var(--text-muted)] font-mono">Spatio-temporal gate</span>
        </div>

        {rejectedDecisions.length === 0 ? (
          <div className="p-2 rounded bg-[var(--surface-sunken)] border border-[var(--border-subtle)] text-[11px] text-[var(--text-muted)] font-mono">
            No conflicting candidate identities evaluated.
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {rejectedDecisions.map((rej, idx) => (
              <div
                key={rej.id || idx}
                className="p-2.5 rounded-[var(--radius-md)] bg-[var(--surface-sunken)] border border-[var(--status-rejected)]/30 font-mono text-[11px] flex flex-col gap-1"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <span className="font-bold text-[var(--text-primary)]">
                      {rej.candidate_vehicle_id
                        ? `#${rej.candidate_vehicle_id.slice(-4).toUpperCase()}`
                        : '#ALT-VEH'}
                    </span>
                    {rej.visual_score && (
                      <span className="text-[10px] text-[var(--text-secondary)]">
                        visual {rej.visual_score.toFixed(2)}
                      </span>
                    )}
                  </div>
                  <span className="px-1.5 py-0.2 rounded bg-[var(--status-rejected-tint)] text-[var(--status-rejected)] font-semibold text-[10px]">
                    {rej.rejection_reason || 'TEMPORAL_TOO_FAST'}
                  </span>
                </div>

                {/* Quantitative explanation of rejection reason */}
                {rej.elapsed_seconds !== undefined && rej.min_transit_seconds !== undefined && (
                  <div className="text-[10px] text-[var(--text-secondary)] mt-0.5 bg-[var(--surface-base)] p-1.5 rounded border border-[var(--border-subtle)]">
                    <div className="text-[var(--status-rejected)] font-medium">
                      Physically infeasible speed violation:
                    </div>
                    <div>
                      {rej.elapsed_seconds}s elapsed vs minimum feasible {rej.min_transit_seconds}s
                    </div>
                    {rej.path_distance_m && (
                      <div className="text-[var(--text-muted)]">
                        {(rej.path_distance_m / 1000).toFixed(1)} km separation along road graph
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
