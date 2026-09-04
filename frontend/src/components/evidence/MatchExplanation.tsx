import React from 'react';
import type { MatchDecision } from '../../types/api';
import { StatusBadge } from '../ui/StatusBadge';
import { Route, XCircle } from 'lucide-react';


/** Plain-language label for a gate rejection code. */
const REJECTION_LABELS: Record<string, string> = {
  TEMPORAL_TOO_FAST: 'Too fast to be possible',
  SAME_CAMERA_TOO_SOON: 'Re-appeared too soon',
  TEMPORAL_EXPIRED: 'Too much time passed',
  NO_PATH: 'No road route between cameras',
  BELOW_THRESHOLD: 'Not similar enough',
  AMBIGUOUS_MARGIN: 'Too close to call',
  OPERATOR_REJECTED: 'Rejected by an operator',
  CLASS_MISMATCH: 'Different type of vehicle',
};

function rejectionLabel(reason?: string | null): string {
  if (!reason) return 'Rejected';
  return REJECTION_LABELS[reason] ?? reason.replace(/_/g, ' ').toLowerCase();
}

function percent(score?: number | null): string | null {
  if (score === null || score === undefined) return null;
  return `${Math.round(score * 100)}%`;
}

/** Implied average speed in km/h, or null when it cannot be derived.
 *  Guards against a missing or zero distance/elapsed rather than dividing by zero. */
function impliedSpeedKmh(distanceM?: number | null, elapsedSeconds?: number | null): number | null {
  if (!distanceM || !elapsedSeconds || distanceM <= 0 || elapsedSeconds <= 0) return null;
  return (distanceM / 1000) / (elapsedSeconds / 3600);
}

/** One or two plain sentences explaining why a candidate was ruled out.
 *  Each reason code gets its own template. */
function rejectionSentences(rej: MatchDecision): string {
  const similar = percent(rej.visual_score);
  const opener = similar ? `Looks ${similar} similar, but ` : '';
  const elapsed = rej.elapsed_seconds;
  const distanceKm =
    rej.path_distance_m && rej.path_distance_m > 0 ? rej.path_distance_m / 1000 : null;

  switch (rej.rejection_reason) {
    case 'TEMPORAL_TOO_FAST': {
      const speed = impliedSpeedKmh(rej.path_distance_m, elapsed);
      if (distanceKm !== null && elapsed) {
        const speedClause = speed
          ? ` (about ${Math.round(speed).toLocaleString()} km/h)`
          : '';
        return `${opener}this vehicle would have had to cover ${distanceKm.toFixed(1)} km in ${elapsed} seconds${speedClause}. Ruled out as physically impossible.`;
      }
      if (elapsed && rej.min_transit_seconds) {
        return `${opener}only ${elapsed} seconds passed, and the quickest possible trip between these cameras takes ${rej.min_transit_seconds} seconds. Ruled out as physically impossible.`;
      }
      return `${opener}the vehicle could not have travelled between these cameras that quickly. Ruled out as physically impossible.`;
    }

    case 'SAME_CAMERA_TOO_SOON': {
      const minSeconds = rej.min_transit_seconds;
      const gap = elapsed ? `just ${elapsed} seconds later` : 'again very shortly afterwards';
      const rule = minSeconds
        ? ` A vehicle cannot pass this camera twice in under ${minSeconds} seconds, so this match was rejected.`
        : ' A vehicle cannot pass the same camera twice that quickly, so this match was rejected.';
      return `Seen again at the same camera ${gap}.${rule}`;
    }

    case 'TEMPORAL_EXPIRED': {
      const window = rej.max_transit_seconds;
      if (elapsed && window) {
        return `${opener}${elapsed} seconds passed, well beyond the ${window} seconds this trip should take. Too long a gap to treat as the same journey.`;
      }
      return `${opener}too much time passed between the two sightings to treat them as the same journey.`;
    }

    case 'NO_PATH':
      return `${opener}there is no known road route between these two cameras, so the vehicle could not have made the trip.`;

    case 'CLASS_MISMATCH':
      return `${opener}the two sightings are different types of vehicle, so they cannot be the same one.`;

    case 'BELOW_THRESHOLD':
      return similar
        ? `Only ${similar} similar, which is below the level needed to call it a match.`
        : 'Not similar enough to call it a match.';

    case 'AMBIGUOUS_MARGIN':
      return `${opener}another candidate scored almost identically, so this match was too close to call.`;

    case 'OPERATOR_REJECTED':
      return 'An operator reviewed this candidate and rejected it.';

    default:
      return similar
        ? `Looks ${similar} similar, but the spatio-temporal gate ruled this candidate out.`
        : 'The spatio-temporal gate ruled this candidate out.';
  }
}

interface MatchExplanationProps {
  decisions: MatchDecision[];
  cameraCode?: string;
  fromCameraCode?: string;
}

export const MatchExplanation: React.FC<MatchExplanationProps> = ({
  decisions,
  cameraCode = '—',
  fromCameraCode = '—',
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
              Rejected matches ({rejectedDecisions.length})
            </span>
          </div>
          <span className="text-[10px] text-[var(--text-muted)] font-mono">
            Blocked by the spatio-temporal gate
          </span>
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
                    {/* Explicit null check, not a truthiness test: a 0.00 score
                        would otherwise render a stray "0" instead of the span. */}
                    {percent(rej.visual_score) !== null && (
                      <span className="text-[10px] text-[var(--text-secondary)]">
                        visual {percent(rej.visual_score)}
                      </span>
                    )}
                  </div>
                  <span className="px-1.5 py-0.2 rounded bg-[var(--status-rejected-tint)] text-[var(--status-rejected)] font-semibold text-[10px]">
                    {rejectionLabel(rej.rejection_reason)}
                  </span>
                </div>

                {/* Plain-language explanation, templated per rejection reason */}
                <div className="text-[10px] leading-relaxed text-[var(--text-secondary)] mt-0.5 bg-[var(--surface-base)] p-1.5 rounded border border-[var(--border-subtle)]">
                  {rejectionSentences(rej)}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
