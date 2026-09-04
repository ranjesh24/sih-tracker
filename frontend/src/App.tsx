import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { TopBar } from './components/common/TopBar';
import { LiveWallPage } from './pages/LiveWallPage';
import { TrajectoryPage } from './pages/TrajectoryPage';
import { EvidencePage } from './pages/EvidencePage';
import { UploadPage } from './pages/UploadPage';
import { usePollingSightings } from './hooks/usePollingSightings';
import { api } from './lib/api';
import type { Camera, Vehicle } from './types/api';

/** display_ref of the vehicle created by backend/scripts/seed_demo.py. */
const SEEDED_DEMO_REF = '#A47F';

export const App: React.FC = () => {
  const [activeVehicleId, setActiveVehicleId] = useState<string>('');
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [cameras, setCameras] = useState<Camera[]>([]);

  // 1-second polling hook for live events per user requirements
  const { events, flashingCameraCode, isLive, lastUpdated } = usePollingSightings(1500);

  // Only cameras with an uploaded video in the current batch. Keyed on the
  // videos table, not sightings: seeded sightings would otherwise make every
  // camera look live. Re-polled so a tile appears as soon as a video lands.
  useEffect(() => {
    let isMounted = true;
    async function loadCameras() {
      const data = await api.getCameras({ has_video: true });
      if (isMounted) setCameras(data);
    }
    loadCameras();
    const timer = setInterval(loadCameras, 5000);
    return () => {
      isMounted = false;
      clearInterval(timer);
    };
  }, []);

  // Real vehicles for the selector. Without this the app requested ids that do
  // not exist and fell back to fixture data, which is why the evidence crop was
  // always empty.
  //
  // The default selection is the vehicle seen at the MOST cameras, so the
  // trajectory map draws a multi-point path on first load — the behaviour the
  // hardcoded 'veh-01' used to get from the mock fallback, now from real data.
  // A single-sighting vehicle would render one lonely marker instead.
  useEffect(() => {
    let isMounted = true;
    async function loadVehicles() {
      const page = await api.getVehicles({ limit: 25 });
      if (!isMounted) return;

      // Seeded demo vehicle pinned first so the presentation always opens on
      // the multi-camera trajectory; everything else by how many cameras it
      // reached, so the map has a path to draw rather than a lone marker.
      const byReach = [...page.items].sort((a, b) => {
        const aSeed = a.display_ref === SEEDED_DEMO_REF ? 0 : 1;
        const bSeed = b.display_ref === SEEDED_DEMO_REF ? 0 : 1;
        return (
          aSeed - bSeed ||
          (b.camera_count ?? 0) - (a.camera_count ?? 0) ||
          (b.sighting_count ?? 0) - (a.sighting_count ?? 0)
        );
      });

      setVehicles(byReach);
      setActiveVehicleId((current) => current || byReach[0]?.id || '');
    }
    loadVehicles();
    const timer = setInterval(loadVehicles, 5000);
    return () => {
      isMounted = false;
      clearInterval(timer);
    };
  }, []);

  return (
    <BrowserRouter>
      <div className="flex flex-col h-screen w-screen overflow-hidden bg-[var(--surface-base)] text-[var(--text-primary)]">
        {/* TopBar with Navigation and Connection Status */}
        <TopBar
          status={isLive ? 'live' : 'offline'}
          cameraCount={cameras.length}
          indexSize={154}
          lastUpdated={lastUpdated}
          activeVehicleId={activeVehicleId}
          vehicles={vehicles}
          onSelectVehicle={(id) => setActiveVehicleId(id)}
        />

        {/* Primary Workspace (The Three Core Screens) */}
        <main className="flex-1 overflow-hidden flex flex-col">
          <Routes>
            <Route
              path="/"
              element={
                <LiveWallPage
                  cameras={cameras}
                  events={events}
                  flashingCameraCode={flashingCameraCode}
                />
              }
            />
            <Route
              path="/vehicles/:vehicleId"
              element={<TrajectoryPage cameras={cameras} />}
            />
            <Route
              path="/evidence/:vehicleId"
              element={<EvidencePage cameras={cameras} />}
            />
            <Route path="/upload" element={<UploadPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
};
