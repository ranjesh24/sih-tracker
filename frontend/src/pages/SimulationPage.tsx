import React, { useState, useEffect, useRef, useCallback } from 'react';
import { MapContainer, TileLayer, Marker, Polyline, Popup, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { Play, Pause, RotateCcw, Locate } from 'lucide-react';

// --- Camera locations (Patna, matching seed_cameras.py) ---
const CAMERAS = [
  { id: 'CAM-01', name: 'Dak Bungalow Chauraha', lat: 25.6093, lng: 85.1376 },
  { id: 'CAM-02', name: 'Income Tax Golambar', lat: 25.6138, lng: 85.1322 },
  { id: 'CAM-03', name: 'Gandhi Maidan Gate 1', lat: 25.6205, lng: 85.1441 },
];

// --- Simulated routes with intermediate road-like waypoints ---
const ROUTES = [
  {
    id: 'route-1',
    label: 'White Sedan',
    color: 'var(--accent-text)',
    durationMs: 12000,
    path: [
      { lat: 25.6093, lng: 85.1376 }, // CAM-01
      { lat: 25.6098, lng: 85.1365 },
      { lat: 25.6108, lng: 85.1352 },
      { lat: 25.6120, lng: 85.1340 },
      { lat: 25.6130, lng: 85.1330 },
      { lat: 25.6138, lng: 85.1322 }, // CAM-02
      { lat: 25.6148, lng: 85.1330 },
      { lat: 25.6160, lng: 85.1350 },
      { lat: 25.6172, lng: 85.1375 },
      { lat: 25.6185, lng: 85.1400 },
      { lat: 25.6195, lng: 85.1420 },
      { lat: 25.6205, lng: 85.1441 }, // CAM-03
    ],
  },
  {
    id: 'route-2',
    label: 'Yellow Auto',
    color: 'var(--status-ambiguous)',
    durationMs: 18000,
    path: [
      { lat: 25.6205, lng: 85.1441 }, // CAM-03
      { lat: 25.6198, lng: 85.1425 },
      { lat: 25.6185, lng: 85.1405 },
      { lat: 25.6170, lng: 85.1385 },
      { lat: 25.6155, lng: 85.1370 },
      { lat: 25.6138, lng: 85.1355 },
      { lat: 25.6120, lng: 85.1345 },
      { lat: 25.6105, lng: 85.1355 },
      { lat: 25.6093, lng: 85.1376 }, // CAM-01
    ],
  },
  {
    id: 'route-3',
    label: 'Blue Truck',
    color: '#5b9bd5',
    durationMs: 22000,
    path: [
      { lat: 25.6138, lng: 85.1322 }, // CAM-02
      { lat: 25.6128, lng: 85.1335 },
      { lat: 25.6118, lng: 85.1350 },
      { lat: 25.6108, lng: 85.1365 },
      { lat: 25.6093, lng: 85.1376 }, // CAM-01
    ],
  },
];

function lerp(a: number, b: number, t: number) {
  return a + (b - a) * t;
}

function interpolateAlongPath(path: { lat: number; lng: number }[], progress: number): { lat: number; lng: number } {
  if (progress <= 0) return path[0];
  if (progress >= 1) return path[path.length - 1];

  const totalSegments = path.length - 1;
  const rawIdx = progress * totalSegments;
  const segIdx = Math.floor(rawIdx);
  const segT = rawIdx - segIdx;

  const from = path[Math.min(segIdx, totalSegments)];
  const to = path[Math.min(segIdx + 1, totalSegments)];
  return { lat: lerp(from.lat, to.lat, segT), lng: lerp(from.lng, to.lng, segT) };
}

function trailUpTo(path: { lat: number; lng: number }[], progress: number): [number, number][] {
  if (progress <= 0) return [[path[0].lat, path[0].lng]];
  const totalSegments = path.length - 1;
  const rawIdx = progress * totalSegments;
  const segIdx = Math.floor(rawIdx);
  const segT = rawIdx - segIdx;

  const pts: [number, number][] = [];
  for (let i = 0; i <= segIdx && i < path.length; i++) {
    pts.push([path[i].lat, path[i].lng]);
  }
  if (segIdx < totalSegments) {
    const from = path[segIdx];
    const to = path[segIdx + 1];
    pts.push([lerp(from.lat, to.lat, segT), lerp(from.lng, to.lng, segT)]);
  }
  return pts;
}

function createVehicleDot(color: string) {
  return L.divIcon({
    html: `<div style="
      width: 14px; height: 14px; border-radius: 50%;
      background: ${color}; border: 2px solid white;
      box-shadow: 0 0 8px ${color}, 0 2px 4px rgba(0,0,0,0.4);
    "></div>`,
    className: '',
    iconSize: [14, 14],
    iconAnchor: [7, 7],
  });
}

function createCameraIcon(label: string) {
  return L.divIcon({
    html: `<div style="
      display: flex; align-items: center; justify-content: center;
      width: 28px; height: 28px; border-radius: 6px;
      background: var(--surface-overlay); border: 1.5px solid var(--border-strong);
      font-family: ui-monospace, monospace; font-size: 10px; font-weight: 700;
      color: var(--text-primary); box-shadow: 0 2px 6px rgba(0,0,0,0.3);
    ">${label}</div>`,
    className: '',
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  });
}

function FitBounds() {
  const map = useMap();
  useEffect(() => {
    const bounds = L.latLngBounds(CAMERAS.map(c => [c.lat, c.lng]));
    map.fitBounds(bounds, { padding: [60, 60], maxZoom: 15 });
  }, [map]);
  return null;
}

function RecenterButton() {
  const map = useMap();
  const recenter = useCallback(() => {
    const bounds = L.latLngBounds(CAMERAS.map(c => [c.lat, c.lng]));
    map.fitBounds(bounds, { padding: [60, 60], maxZoom: 15, animate: true });
  }, [map]);
  return (
    <button
      onClick={recenter}
      className="absolute bottom-4 right-4 z-[1000] p-2 bg-[var(--surface-overlay)] border border-[var(--border-default)] rounded-[var(--radius-sm)] hover:bg-[var(--surface-hover)] cursor-pointer"
      title="Recenter"
    >
      <Locate className="w-4 h-4 text-[var(--text-secondary)]" />
    </button>
  );
}

export const SimulationPage: React.FC = () => {
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState<number[]>(ROUTES.map(() => 0));
  const startTimeRef = useRef<number | null>(null);
  const rafRef = useRef<number>(0);
  const [staggerOffsets] = useState(() => ROUTES.map((_, i) => i * 2000));

  const reset = useCallback(() => {
    setPlaying(false);
    setProgress(ROUTES.map(() => 0));
    startTimeRef.current = null;
    cancelAnimationFrame(rafRef.current);
  }, []);

  useEffect(() => {
    if (!playing) return;

    if (startTimeRef.current === null) {
      startTimeRef.current = performance.now();
    }
    const start = startTimeRef.current;

    const tick = (now: number) => {
      const elapsed = now - start;
      const newProgress = ROUTES.map((route, i) => {
        const routeElapsed = elapsed - staggerOffsets[i];
        if (routeElapsed <= 0) return 0;
        return Math.min(routeElapsed / route.durationMs, 1);
      });
      setProgress(newProgress);

      if (newProgress.every(p => p >= 1)) {
        setPlaying(false);
        return;
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [playing, staggerOffsets]);

  const allDone = progress.every(p => p >= 1);

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-[var(--surface-base)]">
      {/* Header */}
      <div className="px-4 py-2.5 bg-[var(--surface-raised)] border-b border-[var(--border-default)] flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <h1 className="text-sm font-semibold text-[var(--text-primary)]">Trajectory simulation</h1>
          <span className="text-[11px] font-mono text-[var(--text-muted)]">
            {ROUTES.length} vehicles / {CAMERAS.length} cameras
          </span>
          {playing && (
            <span className="text-[11px] px-1.5 py-0.5 rounded-[var(--radius-sm)] font-mono"
              style={{ color: 'var(--status-confirmed)', background: 'color-mix(in srgb, var(--status-confirmed) 14%, transparent)' }}>
              running
            </span>
          )}
          {allDone && (
            <span className="text-[11px] px-1.5 py-0.5 rounded-[var(--radius-sm)] font-mono"
              style={{ color: 'var(--accent-text)', background: 'color-mix(in srgb, var(--accent-text) 14%, transparent)' }}>
              complete
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => { if (allDone) { reset(); setTimeout(() => setPlaying(true), 50); } else setPlaying(p => !p); }}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-[var(--accent)] text-[var(--text-inverse)] rounded-[var(--radius-sm)] hover:bg-[var(--accent-hover)] cursor-pointer"
          >
            {playing ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
            <span>{allDone ? 'Replay' : playing ? 'Pause' : 'Play'}</span>
          </button>
          <button
            onClick={reset}
            className="p-1.5 bg-[var(--surface-sunken)] border border-[var(--border-default)] rounded-[var(--radius-sm)] hover:bg-[var(--surface-hover)] cursor-pointer"
            title="Reset"
          >
            <RotateCcw className="w-3.5 h-3.5 text-[var(--text-secondary)]" />
          </button>
        </div>
      </div>

      {/* Map */}
      <div style={{ flex: 1, position: 'relative', minHeight: 0 }}>
        <div style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }}>
        <MapContainer
          center={[25.6140, 85.1380]}
          zoom={15}
          style={{ width: '100%', height: '100%' }}
          scrollWheelZoom={true}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
            maxZoom={19}
          />
          <FitBounds />

          {/* Camera markers */}
          {CAMERAS.map((cam, i) => (
            <Marker key={cam.id} position={[cam.lat, cam.lng]} icon={createCameraIcon(`C${i + 1}`)}>
              <Popup>
                <div className="text-xs font-mono p-1">
                  <div className="font-bold">{cam.id}</div>
                  <div className="text-[var(--text-secondary)]">{cam.name}</div>
                </div>
              </Popup>
            </Marker>
          ))}

          {/* Route trails + vehicle dots */}
          {ROUTES.map((route, i) => {
            const p = progress[i];
            if (p <= 0) return null;
            const trail = trailUpTo(route.path, p);
            const pos = interpolateAlongPath(route.path, p);

            return (
              <React.Fragment key={route.id}>
                {/* Casing */}
                <Polyline positions={trail} pathOptions={{ color: 'rgba(14,16,18,0.7)', weight: 6 }} />
                {/* Trail */}
                <Polyline positions={trail} pathOptions={{ color: route.color, weight: 3, opacity: 0.85 }} />
                {/* Vehicle dot */}
                <Marker position={[pos.lat, pos.lng]} icon={createVehicleDot(route.color)} />
              </React.Fragment>
            );
          })}
        </MapContainer>
        </div>

        <RecenterButton />

        {/* Route legend */}
        <div className="absolute top-3 right-3 z-[1000] bg-[var(--surface-overlay)]/95 border border-[var(--border-default)] rounded-[var(--radius-md)] p-2.5 shadow-md flex flex-col gap-2 text-[11px] font-mono pointer-events-none select-none">
          <div className="text-[10px] text-[var(--text-secondary)] font-bold">Vehicles</div>
          {ROUTES.map((route, i) => (
            <div key={route.id} className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full shrink-0" style={{ background: route.color, border: '1.5px solid white' }} />
              <span className="text-[var(--text-primary)]">{route.label}</span>
              <span className="text-[var(--text-muted)] ml-auto">{Math.round(progress[i] * 100)}%</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
