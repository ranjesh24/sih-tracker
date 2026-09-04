import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { TrajectoryMap } from '../components/map/TrajectoryMap';
import { EvidencePanel } from '../components/evidence/EvidencePanel';
import { PlateBadge } from '../components/ui/PlateBadge';
import { StatusBadge } from '../components/ui/StatusBadge';
import { api } from '../lib/api';
import { placeCameras, placePoints, scopePoints } from '../lib/cameraScope';
import type { Camera, Vehicle, TrajectoryRead, SightingDetailRead } from '../types/api';
import { Clock, ChevronRight } from 'lucide-react';
import { cn } from '../lib/cn';

interface TrajectoryPageProps {
  /** Cameras with an uploaded video in the current batch. Supplied by App so
      the map can never disagree with the live wall or the evidence tabs. */
  cameras: Camera[];
}

export const TrajectoryPage: React.FC<TrajectoryPageProps> = ({ cameras }) => {
  const { vehicleId = 'veh-01' } = useParams<{ vehicleId: string }>();

  const [vehicle, setVehicle] = useState<Vehicle | null>(null);
  const [trajectory, setTrajectory] = useState<TrajectoryRead | null>(null);
  const [selectedSightingId, setSelectedSightingId] = useState<string | null>(null);
  const [sightingDetail, setSightingDetail] = useState<SightingDetailRead | null>(null);

  // Load vehicle and trajectory data
  useEffect(() => {
    let isMounted = true;
    async function loadData() {
      try {
        const [vehData, trajData] = await Promise.all([
          api.getVehicle(vehicleId),
          // Mock points only when nothing has been uploaded; once any video
          // exists the map shows real data only.
          api.getTrajectory(vehicleId, { allowMock: cameras.length === 0 }),
        ]);
        if (!isMounted) return;

        setVehicle(vehData);
        setTrajectory(trajData);

        const scoped = scopePoints(trajData.points, cameras);
        const initial = scoped.length > 1 ? scoped[1] : scoped[0];
        if (initial) setSelectedSightingId(initial.sighting_id);
      } catch (err) {
        console.error('Failed to load vehicle trajectory:', err);
      }
    }
    loadData();
    return () => {
      isMounted = false;
    };
  }, [vehicleId, cameras]);

  // Load sighting details when selected
  useEffect(() => {
    let isMounted = true;
    if (!selectedSightingId) return;

    async function loadSighting() {
      if (!selectedSightingId) return;
      const detail = await api.getSightingDetail(selectedSightingId);
      if (isMounted) setSightingDetail(detail);
    }
    loadSighting();
    return () => {
      isMounted = false;
    };
  }, [selectedSightingId]);

  // Everything below renders from the scoped set: sightings at cameras that
  // actually have an uploaded video, in timestamp order.
  const points = scopePoints(trajectory?.points || [], cameras);
  const placedPoints = placePoints(points, cameras);
  const placedCameras = placeCameras(cameras);
  const hops = (trajectory?.hops || []).slice(0, Math.max(points.length - 1, 0));

  // A new batch can drop the selected camera; fall back to the first point.
  useEffect(() => {
    if (points.length === 0) return;
    if (!points.some((p) => p.sighting_id === selectedSightingId)) {
      setSelectedSightingId(points[0].sighting_id);
    }
  }, [points, selectedSightingId]);

  const selectedIndex = points.findIndex((p) => p.sighting_id === selectedSightingId);
  const selectedPoint = selectedIndex >= 0 ? points[selectedIndex] : points[0] || null;
  const previousPoint = selectedIndex > 0 ? points[selectedIndex - 1] : null;

  return (
    <div className="flex-1 flex flex-col md:flex-row h-full overflow-hidden bg-[var(--surface-base)]">
      {/* Left Column: Map (top) & Chronological Timeline (bottom) */}
      <div className="flex-1 flex flex-col h-full overflow-hidden border-r border-[var(--border-default)]">
        {/* Vehicle Trajectory Header */}
        <div className="p-3 bg-[var(--surface-raised)] border-b border-[var(--border-default)] flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5">
              <span className="font-mono font-bold text-sm text-[var(--accent-text)]">
                {vehicle?.display_ref || '#A47F'}
              </span>
              <PlateBadge plate={vehicle?.canonical_plate} size="md" />
            </div>

            <div className="hidden sm:flex items-center gap-2 text-xs font-mono text-[var(--text-secondary)] border-l border-[var(--border-subtle)] pl-3">
              <span>Class: {vehicle?.vehicle_class || 'car'}</span>
              <span>•</span>
              <span>{points.length} sightings</span>
              <span>•</span>
              <span>{hops.length} camera hops</span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <StatusBadge
              status={hops.some((h) => h.confidence === 'ambiguous') ? 'ambiguous' : 'confirmed'}
              label={
                hops.some((h) => h.confidence === 'ambiguous')
                  ? 'Ambiguous segment'
                  : 'Spatially feasible'
              }
            />
          </div>
        </div>

        {/* Map Region (Fills top) */}
        <div className="flex-1 min-h-[340px] relative p-3">
          <TrajectoryMap
            cameras={placedCameras}
            points={placedPoints}
            hops={hops}
            selectedPointId={selectedSightingId}
            onSelectPoint={(id) => setSelectedSightingId(id)}
          />
        </div>

        {/* Sighting Timeline (Bottom Section) per design.md §6 & appflow.md §A4 */}
        <div className="h-[210px] shrink-0 border-t border-[var(--border-default)] bg-[var(--surface-raised)] flex flex-col">
          <div className="px-3 py-2 border-b border-[var(--border-subtle)] flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Clock className="w-3.5 h-3.5 text-[var(--text-secondary)]" />
              <h3 className="text-xs font-semibold text-[var(--text-primary)] uppercase tracking-wider">
                Chronological sighting sequence
              </h3>
            </div>
            <span className="text-[11px] font-mono text-[var(--text-muted)]">
              Click hop to inspect evidence
            </span>
          </div>

          {/* Sequence List */}
          <div className="flex-1 overflow-y-auto p-2 flex flex-col gap-1.5">
            {points.map((pt, idx) => {
              const isSelected = selectedSightingId === pt.sighting_id;
              const hop = idx > 0 ? hops[idx - 1] : null;

              return (
                <div
                  key={pt.sighting_id}
                  onClick={() => setSelectedSightingId(pt.sighting_id)}
                  className={cn(
                    'p-2 rounded-[var(--radius-sm)] flex items-center justify-between font-mono text-xs cursor-pointer border transition-none select-none',
                    isSelected
                      ? 'bg-[var(--accent-tint)] border-[var(--accent)] text-[var(--text-primary)]'
                      : 'bg-[var(--surface-sunken)] border-[var(--border-subtle)] hover:border-[var(--border-strong)] text-[var(--text-secondary)]'
                  )}
                >
                  <div className="flex items-center gap-3">
                    {/* Sequence Number Circle */}
                    <div
                      className={cn(
                        'w-5 h-5 rounded-full flex items-center justify-center font-bold text-[11px]',
                        isSelected
                          ? 'bg-[var(--accent)] text-[var(--text-inverse)]'
                          : 'bg-[var(--surface-hover)] text-[var(--text-secondary)]'
                      )}
                    >
                      {idx + 1}
                    </div>

                    <div className="flex flex-col">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-[var(--text-primary)]">
                          {pt.camera_code}
                        </span>
                        <span className="text-[11px] text-[var(--text-muted)]">
                          {new Date(pt.timestamp).toLocaleTimeString([], { hour12: false })}
                        </span>
                      </div>
                      {hop && (
                        <span className="text-[10px] text-[var(--text-secondary)]">
                          Transit: {hop.elapsed_seconds}s (feasible: {hop.min_transit_seconds}–{hop.max_transit_seconds}s)
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <PlateBadge plate={pt.plate_text_norm} size="sm" />
                    {pt.match_method && (
                      <StatusBadge
                        status={pt.match_method === 'PLATE_EXACT' ? 'confirmed' : 'probable'}
                        label={pt.match_method}
                      />
                    )}
                    <ChevronRight className="w-3.5 h-3.5 text-[var(--text-muted)]" />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Right Column: Evidence Panel (Fixed 380px) */}
      <EvidencePanel
        sightingDetail={sightingDetail}
        selectedPoint={selectedPoint}
        previousPoint={previousPoint}
      />
    </div>
  );
};
