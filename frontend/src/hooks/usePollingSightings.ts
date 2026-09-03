import { useState, useEffect, useRef, useCallback } from 'react';
import { api } from '../lib/api';
import type { Sighting } from '../types/api';
import { MOCK_SIGHTINGS } from '../mocks/mockData';

export interface LiveEventItem {
  id: string;
  type: 'sighting' | 'rejected' | 'ambiguous';
  timestamp: string;
  cameraCode: string;
  vehicleRef?: string | null;
  plateText?: string | null;
  method?: string | null;
  score?: number | null;
  sightingId?: string;
  vehicleId?: string | null;
  rejectionReason?: string | null;
  elapsedSeconds?: number | null;
  minTransitSeconds?: number | null;
}

export function usePollingSightings(intervalMs: number = 1500) {
  const [sightings, setSightings] = useState<Sighting[]>(MOCK_SIGHTINGS);
  const [events, setEvents] = useState<LiveEventItem[]>([]);
  const [flashingCameraCode, setFlashingCameraCode] = useState<string | null>(null);
  const [isLive, setIsLive] = useState<boolean>(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(new Date());
  const seenSightingIds = useRef<Set<string>>(new Set(MOCK_SIGHTINGS.map((s) => s.id)));
  const flashTimeoutRef = useRef<number | null>(null);

  // Initialize event feed with realistic pre-seeded events including gate rejection
  useEffect(() => {
    const initialEvents: LiveEventItem[] = [
      {
        id: 'evt-rej-1',
        type: 'rejected',
        timestamp: '2026-09-04T00:26:25Z',
        cameraCode: 'CAM-02',
        vehicleRef: '#A47F',
        rejectionReason: 'TEMPORAL_TOO_FAST',
        elapsedSeconds: 14,
        minTransitSeconds: 312,
        sightingId: 'sight-02',
        vehicleId: 'veh-01',
      },
      {
        id: 'evt-sight-3',
        type: 'sighting',
        timestamp: '2026-09-04T00:26:18Z',
        cameraCode: 'CAM-03',
        vehicleRef: '#A47F',
        plateText: 'BR01AB1234',
        method: 'VISUAL',
        score: 0.84,
        sightingId: 'sight-03',
        vehicleId: 'veh-01',
      },
      {
        id: 'evt-sight-2',
        type: 'sighting',
        timestamp: '2026-09-04T00:18:14Z',
        cameraCode: 'CAM-02',
        vehicleRef: '#A47F',
        plateText: null,
        method: 'VISUAL',
        score: 0.88,
        sightingId: 'sight-02',
        vehicleId: 'veh-01',
      },
      {
        id: 'evt-sight-1',
        type: 'sighting',
        timestamp: '2026-09-04T00:10:02Z',
        cameraCode: 'CAM-01',
        vehicleRef: '#A47F',
        plateText: 'BR01AB1234',
        method: 'PLATE_EXACT',
        score: 1.0,
        sightingId: 'sight-01',
        vehicleId: 'veh-01',
      },
    ];
    setEvents(initialEvents);
  }, []);

  const triggerFlash = useCallback((cameraCode: string) => {
    setFlashingCameraCode(cameraCode);
    if (flashTimeoutRef.current) window.clearTimeout(flashTimeoutRef.current);
    flashTimeoutRef.current = window.setTimeout(() => {
      setFlashingCameraCode(null);
    }, 600);
  }, []);

  // Polling loop
  useEffect(() => {
    let isMounted = true;

    const poll = async () => {
      try {
        const response = await api.getSightings({ limit: 20 });
        if (!isMounted) return;

        setIsLive(true);
        setLastUpdated(new Date());

        const incoming = response.items;
        let hasNew = false;
        let newestCamCode: string | null = null;

        incoming.forEach((s) => {
          if (!seenSightingIds.current.has(s.id)) {
            seenSightingIds.current.add(s.id);
            hasNew = true;
            if (s.camera_code) newestCamCode = s.camera_code;

            // Prepend new event
            setEvents((prev) => [
              {
                id: `evt-${s.id}-${Date.now()}`,
                type: s.resolution_status === 'ambiguous' ? 'ambiguous' : 'sighting',
                timestamp: s.first_frame_at,
                cameraCode: s.camera_code || 'CAM-01',
                vehicleRef: s.vehicle_id ? `#${s.vehicle_id.slice(-4).toUpperCase()}` : '#NEW',
                plateText: s.plate_text_norm,
                method: s.match_method,
                score: s.match_score,
                sightingId: s.id,
                vehicleId: s.vehicle_id,
              },
              ...prev.slice(0, 99),
            ]);
          }
        });

        if (hasNew) {
          setSightings(incoming);
          if (newestCamCode) triggerFlash(newestCamCode);
        }
      } catch {
        if (!isMounted) return;
        setIsLive(false);
      }
    };

    const timer = setInterval(poll, intervalMs);
    return () => {
      isMounted = false;
      clearInterval(timer);
      if (flashTimeoutRef.current) clearTimeout(flashTimeoutRef.current);
    };
  }, [intervalMs, triggerFlash]);

  return {
    sightings,
    events,
    flashingCameraCode,
    isLive,
    lastUpdated,
    triggerFlash,
  };
}
