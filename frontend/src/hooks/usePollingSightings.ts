import { useState, useEffect, useRef, useCallback } from 'react';
import { api } from '../lib/api';
import type { Sighting } from '../types/api';

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
  const [sightings, setSightings] = useState<Sighting[]>([]);
  const [events, setEvents] = useState<LiveEventItem[]>([]);
  const [flashingCameraCode, setFlashingCameraCode] = useState<string | null>(null);
  const [isLive, setIsLive] = useState<boolean>(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(new Date());
  const seenSightingIds = useRef<Set<string>>(new Set());
  const flashTimeoutRef = useRef<number | null>(null);

  // No pre-seeded events. The stream previously started with four fabricated
  // entries naming CAM-01/02/03, which put cameras into the ingest feed that had
  // no uploaded video and contradicted the wall. It now shows only what polling
  // actually returns.

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
                cameraCode: s.camera_code ?? '—',
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
