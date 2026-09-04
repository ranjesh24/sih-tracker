import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { TopBar } from './components/common/TopBar';
import { LiveWallPage } from './pages/LiveWallPage';
import { TrajectoryPage } from './pages/TrajectoryPage';
import { EvidencePage } from './pages/EvidencePage';
import { UploadPage } from './pages/UploadPage';
import { SimulationPage } from './pages/SimulationPage';
import { usePollingSightings } from './hooks/usePollingSightings';
import { api } from './lib/api';
import type { Camera } from './types/api';
import { MOCK_CAMERAS } from './mocks/mockData';

export const App: React.FC = () => {
  const [activeVehicleId, setActiveVehicleId] = useState<string>('veh-01');
  const [cameras, setCameras] = useState<Camera[]>(MOCK_CAMERAS);

  // 1-second polling hook for live events per user requirements
  const { events, flashingCameraCode, isLive, lastUpdated } = usePollingSightings(1500);

  useEffect(() => {
    async function loadCameras() {
      const data = await api.getCameras();
      setCameras(data);
    }
    loadCameras();
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
            <Route path="/vehicles/:vehicleId" element={<TrajectoryPage />} />
            <Route path="/evidence/:vehicleId" element={<EvidencePage />} />
            <Route path="/upload" element={<UploadPage />} />
            <Route path="/sim" element={<SimulationPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
};
