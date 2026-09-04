import axios from 'axios';
import type {
  Camera,
  Vehicle,
  Sighting,
  SightingDetailRead,
  TrajectoryRead,
  MatchDecision,
  PaginatedResponse,
  HealthRead,
} from '../types/api';
import {
  MOCK_VEHICLES,
  MOCK_TRAJECTORIES,
  MOCK_SIGHTING_DETAILS,
} from '../mocks/mockData';

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

/** Absolute URL for a backend-served static asset.
 *
 *  Derived from BASE_URL — the same VITE_API_URL config the rest of this client
 *  uses — rather than a second hardcoded host. It therefore resolves correctly
 *  whatever port the frontend is served from, because it never consults
 *  window.location: only the configured API origin matters.
 *
 *  A same-origin deployment (VITE_API_URL="/api/v1") collapses to a relative
 *  "/static/..." path, which is also correct. */
export function staticAssetUrl(path?: string | null): string | null {
  if (!path) return null;
  if (/^https?:\/\//i.test(path)) return path;
  const origin = BASE_URL.replace(/\/api\/v1\/?$/, '');
  return `${origin}/${path.replace(/^\//, '')}`;
}

export const axiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 8000,
});

export const api = {
  async getHealth(): Promise<HealthRead> {
    try {
      const { data } = await axiosInstance.get<HealthRead>('/system/health');
      return data;
    } catch {
      return { status: 'ok', index_size: 0, camera_count: 0 };
    }
  },

  async getCameras(params?: { has_video?: boolean }): Promise<Camera[]> {
    // No mock fallback: the live wall must show exactly the cameras that have
    // an uploaded video. Falling back to a fixture would invent feeds that do
    // not exist, which is the bug this replaced.
    try {
      const { data } = await axiosInstance.get<Camera[]>('/cameras', { params });
      return data ?? [];
    } catch {
      return [];
    }
  },

  async getVehicles(params?: {
    plate?: string;
    plate_partial?: string;
    from?: string;
    to?: string;
    camera_id?: string;
    vehicle_class?: string;
    min_sightings?: number;
    limit?: number;
    offset?: number;
  }): Promise<PaginatedResponse<Vehicle>> {
    try {
      const { data } = await axiosInstance.get<PaginatedResponse<Vehicle>>('/vehicles', { params });
      if (data && data.items && data.items.length > 0) return data;
      return {
        items: MOCK_VEHICLES,
        total: MOCK_VEHICLES.length,
        limit: params?.limit || 50,
        offset: params?.offset || 0,
      };
    } catch {
      return {
        items: MOCK_VEHICLES,
        total: MOCK_VEHICLES.length,
        limit: params?.limit || 50,
        offset: params?.offset || 0,
      };
    }
  },

  async getVehicle(vehicleId: string): Promise<Vehicle> {
    try {
      const { data } = await axiosInstance.get<Vehicle>(`/vehicles/${vehicleId}`);
      return data;
    } catch {
      const v = MOCK_VEHICLES.find((x) => x.id === vehicleId);
      if (v) return v;
      return MOCK_VEHICLES[0];
    }
  },

  /** @param allowMock false once any video is uploaded: the map must never show
   *  mock points beside real ones. The fallback stays for the zero-upload case,
   *  which is what gives the demo a path to draw before anything is ingested. */
  async getTrajectory(
    vehicleId: string,
    options?: { allowMock?: boolean }
  ): Promise<TrajectoryRead> {
    const allowMock = options?.allowMock !== false;
    const empty: TrajectoryRead = {
      vehicle_id: vehicleId,
      display_ref: '',
      canonical_plate: null,
      points: [],
      hops: [],
    };
    const fallback = () =>
      allowMock
        ? MOCK_TRAJECTORIES[vehicleId] || MOCK_TRAJECTORIES['veh-01']
        : empty;
    try {
      const { data } = await axiosInstance.get<TrajectoryRead>(`/vehicles/${vehicleId}/trajectory`);
      if (data && data.points && data.points.length > 0) return data;
      return fallback();
    } catch {
      return fallback();
    }
  },

  /** Live ingest stream. No mock fallback: its only consumer is the live event
   *  feed, and fixture sightings would name cameras that have no uploaded video,
   *  contradicting the wall. An empty list is the honest answer. */
  async getSightings(params?: {
    from?: string;
    to?: string;
    camera_id?: string;
    limit?: number;
    offset?: number;
  }): Promise<PaginatedResponse<Sighting>> {
    const empty: PaginatedResponse<Sighting> = {
      items: [],
      total: 0,
      limit: params?.limit || 50,
      offset: params?.offset || 0,
    };
    try {
      const { data } = await axiosInstance.get<PaginatedResponse<Sighting>>('/sightings', { params });
      return data ?? empty;
    } catch {
      return empty;
    }
  },

  async getSightingDetail(sightingId: string): Promise<SightingDetailRead> {
    try {
      const { data } = await axiosInstance.get<SightingDetailRead>(`/sightings/${sightingId}`);
      return data;
    } catch {
      return MOCK_SIGHTING_DETAILS[sightingId] || MOCK_SIGHTING_DETAILS['sight-02'];
    }
  },

  async getCandidates(sightingId: string): Promise<MatchDecision[]> {
    try {
      const { data } = await axiosInstance.get<MatchDecision[]>(`/sightings/${sightingId}/candidates`);
      return data;
    } catch {
      return MOCK_SIGHTING_DETAILS[sightingId]?.decisions || MOCK_SIGHTING_DETAILS['sight-02'].decisions;
    }
  },
};
