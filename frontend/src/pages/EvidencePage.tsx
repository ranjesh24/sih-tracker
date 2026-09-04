import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { api, staticAssetUrl } from '../lib/api';
import { scopePoints } from '../lib/cameraScope';
import type { Camera, Vehicle, TrajectoryRead, SightingDetailRead } from '../types/api';
import { MatchExplanation } from '../components/evidence/MatchExplanation';
import { PlateBadge } from '../components/ui/PlateBadge';
import { FileSearch, ArrowLeft } from 'lucide-react';
import { cn } from '../lib/cn';

interface EvidencePageProps {
  /** Cameras with an uploaded video in the current batch, from App. The tab
      strip is exactly this set, so it always agrees with the wall and the map. */
  cameras: Camera[];
}

export const EvidencePage: React.FC<EvidencePageProps> = ({ cameras }) => {
  const { vehicleId = 'veh-01' } = useParams<{ vehicleId: string }>();
  const navigate = useNavigate();

  const [vehicle, setVehicle] = useState<Vehicle | null>(null);
  const [trajectory, setTrajectory] = useState<TrajectoryRead | null>(null);
  const [selectedSightingId, setSelectedSightingId] = useState<string>('');
  const [sightingDetail, setSightingDetail] = useState<SightingDetailRead | null>(null);

  useEffect(() => {
    let isMounted = true;
    async function loadData() {
      try {
        const [vehData, trajData] = await Promise.all([
          api.getVehicle(vehicleId),
          api.getTrajectory(vehicleId, { allowMock: cameras.length === 0 }),
        ]);
        if (!isMounted) return;
        setVehicle(vehData);
        setTrajectory(trajData);

        const scoped = scopePoints(trajData.points, cameras);
        // Preserve the user's choice across polls. This effect re-runs whenever
        // the polled `cameras` array changes identity (every few seconds), and
        // it used to overwrite the selection each time — which is why a click on
        // CAM-01 snapped back on its own. Only choose for the user when there is
        // no valid selection: first load, or the selected camera disappeared.
        setSelectedSightingId((current) => {
          const stillValid = scoped.some((p) => p.sighting_id === current);
          if (stillValid) return current;
          return scoped[0]?.sighting_id ?? '';
        });
      } catch (err) {
        console.error(err);
      }
    }
    loadData();
    return () => {
      isMounted = false;
    };
  }, [vehicleId, cameras]);

  useEffect(() => {
    let isMounted = true;
    async function loadDetail() {
      if (!selectedSightingId) return;
      const data = await api.getSightingDetail(selectedSightingId);
      if (isMounted) setSightingDetail(data);
    }
    loadDetail();
    return () => {
      isMounted = false;
    };
  }, [selectedSightingId]);

  // The crop lives on the trajectory point (per camera hop); fall back to the
  // sighting's own stored path for a sighting opened outside a trajectory.
  const [cropFailed, setCropFailed] = useState(false);
  useEffect(() => {
    setCropFailed(false);
  }, [selectedSightingId]);

  // Tabs come from the scoped set only: a sighting at a camera with no
  // uploaded video is omitted rather than shown as a dead tab.
  const points = scopePoints(trajectory?.points || [], cameras);
  // If a new batch removes the selected camera, fall back to the first
  // available tab rather than rendering a blank panel.
  useEffect(() => {
    if (points.length === 0) return;
    if (!points.some((p) => p.sighting_id === selectedSightingId)) {
      setSelectedSightingId(points[0].sighting_id);
    }
  }, [points, selectedSightingId]);

  const selectedIndex = points.findIndex((p) => p.sighting_id === selectedSightingId);
  const selectedPoint = selectedIndex >= 0 ? points[selectedIndex] : points[0] || null;
  const previousPoint = selectedIndex > 0 ? points[selectedIndex - 1] : null;
  const cropUrl = staticAssetUrl(
    selectedPoint?.crop_url ??
      (sightingDetail?.crop_path ? `/static/${sightingDetail.crop_path}` : null)
  );
  const trackId = selectedPoint?.local_track_id ?? sightingDetail?.local_track_id ?? 88;

  // Kept deliberately: an empty crop box is otherwise silent, and the cause is
  // almost always upstream (no crop_path on the row, or a stale fixture).
  useEffect(() => {
    if (selectedSightingId && !cropUrl) {
      console.warn(
        `[evidence] no crop_url for sighting ${selectedSightingId}; ` +
          'the row has no crop_path, or this is fixture data rather than a DB record.'
      );
    }
  }, [selectedSightingId, cropUrl]);

  return (
    <div className="flex-1 flex flex-col h-full bg-[var(--surface-base)] overflow-y-auto select-none p-4 md:p-6">
      <div className="max-w-5xl mx-auto w-full flex flex-col gap-5">
        {/* Navigation & Header */}
        <div className="flex items-center justify-between pb-3 border-b border-[var(--border-default)]">
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate(`/vehicles/${vehicleId}`)}
              className="p-1.5 rounded-[var(--radius-sm)] bg-[var(--surface-raised)] border border-[var(--border-default)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] cursor-pointer"
            >
              <ArrowLeft className="w-4 h-4" />
            </button>
            <div className="flex flex-col">
              <div className="flex items-center gap-2">
                <FileSearch className="w-4 h-4 text-[var(--accent-text)]" />
                <h1 className="text-base font-bold text-[var(--text-primary)]">
                  Evidence & Match Verification
                </h1>
              </div>
              <span className="text-xs font-mono text-[var(--text-secondary)]">
                Vehicle {vehicle?.display_ref || '#A47F'} — Multi-Camera Decision Audit
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <PlateBadge plate={vehicle?.canonical_plate} size="md" />
          </div>
        </div>

        {/* Sighting Selector Pills */}
        <div className="flex items-center gap-2 overflow-x-auto pb-1">
          {points.map((pt, idx) => (
            <button
              key={pt.sighting_id}
              onClick={() => setSelectedSightingId(pt.sighting_id)}
              className={cn(
                'px-3 py-1.5 rounded-[var(--radius-sm)] text-xs font-mono flex items-center gap-2 border transition-none cursor-pointer',
                selectedSightingId === pt.sighting_id
                  ? 'bg-[var(--accent-tint)] border-[var(--accent)] text-[var(--text-primary)] font-semibold'
                  : 'bg-[var(--surface-raised)] border-[var(--border-subtle)] text-[var(--text-secondary)] hover:border-[var(--border-strong)]'
              )}
            >
              <span className="w-4 h-4 rounded-full bg-[var(--surface-sunken)] flex items-center justify-center text-[10px]">
                {idx + 1}
              </span>
              <span>{pt.camera_code}</span>
              {pt.plate_text_norm ? (
                <span className="text-[10px] text-[var(--accent-text)]">PLATE</span>
              ) : (
                <span className="text-[10px] text-[var(--status-ambiguous)]">VISUAL</span>
              )}
            </button>
          ))}
        </div>

        {/* Main Evidence Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {/* Left Column: Visual Imagery Evidence */}
          <div className="flex flex-col gap-4">
            <div className="p-4 rounded-[var(--radius-md)] bg-[var(--surface-raised)] border border-[var(--border-default)] flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono uppercase font-bold text-[var(--text-primary)]">
                  Crop & Feature Extraction
                </span>
                <span className="text-xs font-mono text-[var(--accent-text)]">
                  {selectedPoint?.camera_code ?? '—'}
                </span>
              </div>

              {/* Best shot image frame */}
              <div className="aspect-video w-full rounded-[var(--radius-md)] bg-[var(--surface-sunken)] border border-[var(--border-subtle)] flex flex-col items-center justify-center relative overflow-hidden">
                {cropUrl && !cropFailed ? (
                  <img
                    src={cropUrl}
                    alt={`Best-shot crop for tracklet ${trackId}`}
                    onError={() => {
                      console.warn(`[evidence] crop failed to load: ${cropUrl}`);
                      setCropFailed(true);
                    }}
                    className="absolute inset-0 w-full h-full object-contain"
                  />
                ) : (
                  <div className="flex flex-col items-center gap-2 text-[var(--text-muted)]">
                    <div className="w-20 h-12 border-2 border-[var(--accent)] rounded bg-[var(--surface-base)] flex items-center justify-center font-mono font-bold text-xs text-[var(--text-primary)]">
                      {selectedPoint?.camera_code}
                    </div>
                  </div>
                )}

                <span className="absolute top-2 left-2 font-mono text-xs text-[var(--text-muted)] bg-black/70 px-1.5 py-0.5 rounded">
                  Tracklet Best Frame (ID: {trackId})
                </span>

                <div className="absolute bottom-2 left-2 right-2 bg-black/80 px-2 py-1 rounded text-[11px] font-mono text-[var(--text-secondary)] flex justify-between">
                  <span>CLASS: {selectedPoint?.vehicle_class ?? sightingDetail?.vehicle_class ?? 'car'}</span>
                  <span>
                    CONF:{' '}
                    {(
                      (selectedPoint?.detection_confidence ??
                        sightingDetail?.detection_confidence ??
                        0.95) * 100
                    ).toFixed(0)}
                    %
                  </span>
                </div>
              </div>

              {/* Plate recognition crop */}
              <div className="p-3 rounded-[var(--radius-sm)] bg-[var(--surface-sunken)] border border-[var(--border-subtle)] flex items-center justify-between">
                <div className="flex flex-col gap-1">
                  <span className="text-[10px] font-mono text-[var(--text-secondary)] uppercase">
                    OCR Result
                  </span>
                  <PlateBadge
                    plate={selectedPoint?.plate_text_norm}
                    confidence={selectedPoint?.plate_confidence}
                    size="md"
                  />
                </div>
                <span className="text-xs font-mono text-[var(--text-muted)]">
                  {selectedPoint?.plate_text_norm ? 'Validated format' : 'No OCR detection'}
                </span>
              </div>
            </div>
          </div>

          {/* Right Column: Reasoning & Spatio-Temporal Gate */}
          <div className="p-4 rounded-[var(--radius-md)] bg-[var(--surface-raised)] border border-[var(--border-default)] flex flex-col gap-3">
            <div className="flex items-center justify-between pb-2 border-b border-[var(--border-subtle)]">
              <span className="text-xs font-mono uppercase font-bold text-[var(--text-primary)]">
                Algorithmic Justification
              </span>
              <span className="text-xs font-mono text-[var(--text-secondary)]">
                Graph + Appearance
              </span>
            </div>

            <MatchExplanation
              decisions={sightingDetail?.decisions || []}
              cameraCode={selectedPoint?.camera_code}
              fromCameraCode={previousPoint?.camera_code}
            />
          </div>
        </div>
      </div>
    </div>
  );
};
