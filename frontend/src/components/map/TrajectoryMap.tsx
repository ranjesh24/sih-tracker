import React, { useEffect } from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polyline, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import type { Camera, TrajectoryPoint, TrajectoryHop } from '../../types/api';

interface TrajectoryMapProps {
  cameras: Camera[];
  points: TrajectoryPoint[];
  hops: TrajectoryHop[];
  selectedPointId?: string | null;
  onSelectPoint?: (sightingId: string) => void;
}

// Custom SVG icon generator for numbered camera markers per design.md §7
function createNumberedMarkerIcon(sequenceNumber: number, isSelected: boolean) {
  const bg = isSelected ? 'var(--accent)' : 'var(--surface-overlay)';
  const border = isSelected ? 'var(--accent-text)' : 'var(--border-strong)';
  const text = isSelected ? 'var(--text-primary)' : 'var(--text-secondary)';

  const svgHtml = `
    <div style="position: relative; width: 28px; height: 34px; display: flex; align-items: center; justify-content: center;">
      <svg width="28" height="34" viewBox="0 0 28 34" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M14 0C6.268 0 0 6.268 0 14C0 24.5 14 34 14 34C14 34 28 24.5 28 14C28 6.268 21.732 0 14 0Z" fill="${bg}" stroke="${border}" stroke-width="1.5"/>
      </svg>
      <span style="position: absolute; top: 7px; font-family: ui-monospace, monospace; font-size: 11px; font-weight: 700; color: ${text};">
        ${sequenceNumber}
      </span>
    </div>
  `;

  return L.divIcon({
    html: svgHtml,
    className: 'custom-trajectory-pin',
    iconSize: [28, 34],
    iconAnchor: [14, 34],
    popupAnchor: [0, -32],
  });
}

// Controller component to center and fit bounds automatically
function MapBoundsController({ points }: { points: TrajectoryPoint[] }) {
  const map = useMap();

  useEffect(() => {
    if (points.length > 0) {
      const bounds = L.latLngBounds(points.map((p) => [p.lat, p.lng]));
      map.fitBounds(bounds, { padding: [50, 50], maxZoom: 15 });
    }
  }, [points, map]);

  return null;
}

export const TrajectoryMap: React.FC<TrajectoryMapProps> = ({
  cameras,
  points,
  hops,
  selectedPointId,
  onSelectPoint,
}) => {
  // Center defaults around Patna city center (Bihar)
  const defaultCenter: [number, number] = [25.6138, 85.1376];

  return (
    <div className="relative w-full h-full min-h-[380px] bg-[var(--surface-sunken)] rounded-[var(--radius-md)] overflow-hidden border border-[var(--border-default)]">
      <MapContainer
        center={points.length > 0 ? [points[0].lat, points[0].lng] : defaultCenter}
        zoom={14}
        className="w-full h-full z-10"
        scrollWheelZoom={true}
      >
        {/* Standard OpenStreetMap tiles with control-room dark filter (zero API key, zero watermark) */}
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          className="dark-tiles"
          maxZoom={19}
        />

        <MapBoundsController points={points} />

        {/* Polylines joining consecutive sightings per appflow.md §7 */}
        {hops.map((hop, idx) => {
          const p1 = points[idx];
          const p2 = points[idx + 1];
          if (!p1 || !p2) return null;

          const positions: [number, number][] = [
            [p1.lat, p1.lng],
            [p2.lat, p2.lng],
          ];

          // State styling from appflow.md §7:
          // Confirmed -> solid accent 3px
          // Probable -> solid muted 2px
          // Ambiguous -> dashed amber 2px
          let color = 'var(--accent-text)';
          let weight = 3;
          let dashArray: string | undefined = undefined;

          if (hop.confidence === 'probable') {
            color = 'var(--status-probable)';
            weight = 2;
          } else if (hop.confidence === 'ambiguous') {
            color = 'var(--status-ambiguous)';
            weight = 2;
            dashArray = '6, 6';
          }

          return (
            <React.Fragment key={`hop-${idx}`}>
              {/* 1px casing underneath for contrast per design.md §7 */}
              <Polyline
                positions={positions}
                pathOptions={{ color: 'rgba(14, 16, 18, 0.85)', weight: weight + 2 }}
              />
              {/* Main Confidence Polyline */}
              <Polyline
                positions={positions}
                pathOptions={{ color, weight, dashArray }}
              />
            </React.Fragment>
          );
        })}

        {/* Numbered Camera Markers */}
        {points.map((point, index) => {
          const isSelected = selectedPointId === point.sighting_id;
          const markerIcon = createNumberedMarkerIcon(index + 1, isSelected);

          return (
            <Marker
              key={point.sighting_id}
              position={[point.lat, point.lng]}
              icon={markerIcon}
              eventHandlers={{
                click: () => onSelectPoint && onSelectPoint(point.sighting_id),
              }}
            >
              <Popup className="control-room-popup">
                <div className="p-1 text-xs font-mono">
                  <div className="font-bold text-[var(--text-primary)]">
                    Hop #{index + 1}: {point.camera_code}
                  </div>
                  <div className="text-[var(--text-secondary)] text-[10px]">
                    {new Date(point.timestamp).toLocaleTimeString()}
                  </div>
                  {point.plate_text_norm && (
                    <div className="text-[var(--accent-text)] font-semibold mt-1">
                      Plate: {point.plate_text_norm}
                    </div>
                  )}
                </div>
              </Popup>
            </Marker>
          );
        })}
      </MapContainer>

      {/* Map Legend Overlay (Control-room compact) */}
      <div className="absolute top-3 right-3 z-20 bg-[var(--surface-overlay)]/95 border border-[var(--border-default)] rounded-[var(--radius-md)] p-2.5 shadow-md flex flex-col gap-1.5 text-[11px] font-mono pointer-events-none select-none">
        <div className="text-[10px] uppercase text-[var(--text-secondary)] font-bold">
          Trajectory Hops
        </div>
        <div className="flex items-center gap-2">
          <span className="w-4 h-0.5 bg-[var(--accent-text)]" />
          <span className="text-[var(--text-primary)]">Confirmed (3px solid)</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-4 h-0.5 bg-[var(--status-probable)]" />
          <span className="text-[var(--text-secondary)]">Probable (2px solid)</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-4 h-0.5 border-b border-dashed border-[var(--status-ambiguous)]" />
          <span className="text-[var(--status-ambiguous)]">Ambiguous (2px dashed)</span>
        </div>
      </div>
    </div>
  );
};
