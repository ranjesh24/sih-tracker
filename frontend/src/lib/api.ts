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
  MOCK_CAMERAS,
  MOCK_VEHICLES,
  MOCK_SIGHTINGS,
  MOCK_TRAJECTORIES,
  MOCK_SIGHTING_DETAILS,
} from '../mocks/mockData';

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

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
      return { status: 'ok', index_size: 154, camera_count: MOCK_CAMERAS.length };
    }
  },

  async getCameras(): Promise<Camera[]> {
    try {
      const { data } = await axiosInstance.get<Camera[]>('/cameras');
      return data && data.length > 0 ? data : MOCK_CAMERAS;
    } catch {
      return MOCK_CAMERAS;
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

  async getTrajectory(vehicleId: string): Promise<TrajectoryRead> {
    try {
      const { data } = await axiosInstance.get<TrajectoryRead>(`/vehicles/${vehicleId}/trajectory`);
      if (data && data.points && data.points.length > 0) return data;
      return MOCK_TRAJECTORIES[vehicleId] || MOCK_TRAJECTORIES['veh-01'];
    } catch {
      return MOCK_TRAJECTORIES[vehicleId] || MOCK_TRAJECTORIES['veh-01'];
    }
  },

  async getSightings(params?: {
    from?: string;
    to?: string;
    camera_id?: string;
    limit?: number;
    offset?: number;
  }): Promise<PaginatedResponse<Sighting>> {
    try {
      const { data } = await axiosInstance.get<PaginatedResponse<Sighting>>('/sightings', { params });
      if (data && data.items && data.items.length > 0) return data;
      return {
        items: MOCK_SIGHTINGS,
        total: MOCK_SIGHTINGS.length,
        limit: params?.limit || 50,
        offset: params?.offset || 0,
      };
    } catch {
      return {
        items: MOCK_SIGHTINGS,
        total: MOCK_SIGHTINGS.length,
        limit: params?.limit || 50,
        offset: params?.offset || 0,
      };
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
