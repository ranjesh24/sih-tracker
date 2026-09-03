/* api.ts — TypeScript types matching schema.md and techspec.md §5 */

export type VehicleClass = 'car' | 'motorcycle' | 'bus' | 'truck' | 'auto' | 'other';

export type ResolutionStatus = 'pending' | 'matched' | 'ambiguous' | 'new_vehicle';

export type MatchMethod = 'PLATE_EXACT' | 'PLATE_FUZZY' | 'VISUAL' | 'MANUAL' | 'NEW';

export type MatchOutcome = 'accepted' | 'rejected' | 'ambiguous' | 'superseded';

export type RejectionReason =
  | 'TEMPORAL_TOO_FAST'
  | 'TEMPORAL_EXPIRED'
  | 'NO_PATH'
  | 'SAME_CAMERA_TOO_SOON'
  | 'BELOW_THRESHOLD'
  | 'AMBIGUOUS_MARGIN'
  | 'OPERATOR_REJECTED'
  | 'CLASS_MISMATCH';

export type HopConfidence = 'confirmed' | 'probable' | 'ambiguous';

export interface Camera {
  id: string;
  code: string;
  name: string;
  location_label?: string | null;
  latitude: number;
  longitude: number;
  heading_deg?: number | null;
  stream_uri?: string | null;
  is_active: boolean;
  last_seen_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface Vehicle {
  id: string;
  display_ref: string;
  canonical_plate?: string | null;
  plate_confidence?: number | null;
  plate_is_valid: boolean;
  vehicle_class?: VehicleClass | null;
  dominant_color?: string | null;
  sighting_count: number;
  camera_count: number;
  first_seen_at?: string | null;
  last_seen_at?: string | null;
  status: 'active' | 'merged' | 'archived';
  merged_into_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface Sighting {
  id: string;
  vehicle_id?: string | null;
  camera_id: string;
  camera_code?: string | null;
  local_track_id: number;
  first_frame_at: string;
  last_frame_at: string;
  best_frame_at: string;
  received_at: string;
  frame_count: number;
  bbox_x: number;
  bbox_y: number;
  bbox_w: number;
  bbox_h: number;
  detection_confidence: number;
  vehicle_class: VehicleClass;
  plate_text_raw?: string | null;
  plate_text_norm?: string | null;
  plate_confidence?: number | null;
  plate_is_valid: boolean;
  plate_bbox?: string | null;
  crop_path?: string | null;
  plate_crop_path?: string | null;
  sharpness_score?: number | null;
  resolution_status: ResolutionStatus;
  match_method?: MatchMethod | null;
  match_score?: number | null;
  created_at: string;
}

export interface MatchDecision {
  id: string;
  sighting_id: string;
  candidate_vehicle_id?: string | null;
  candidate_sighting_id?: string | null;
  tier: 'plate' | 'visual';
  outcome: MatchOutcome;
  visual_score?: number | null;
  plate_score?: number | null;
  temporal_score?: number | null;
  fused_score?: number | null;
  runner_up_score?: number | null;
  gate_passed: boolean;
  rejection_reason?: RejectionReason | null;
  elapsed_seconds?: number | null;
  min_transit_seconds?: number | null;
  max_transit_seconds?: number | null;
  path_distance_m?: number | null;
  path_camera_codes?: string | null;
  review_status: 'auto' | 'confirmed' | 'rejected';
  decided_by_user_id?: string | null;
  decided_at?: string | null;
  created_at: string;
}

export interface TrajectoryPoint {
  sighting_id: string;
  camera_id: string;
  camera_code: string;
  lat: number;
  lng: number;
  timestamp: string;
  match_method?: MatchMethod | null;
  match_score?: number | null;
  crop_url?: string | null;
  plate_crop_url?: string | null;
  plate_text_norm?: string | null;
  plate_confidence?: number | null;
}

export interface TrajectoryHop {
  from_camera_code: string;
  to_camera_code: string;
  confidence: HopConfidence;
  elapsed_seconds: number;
  min_transit_seconds: number;
  max_transit_seconds: number;
  distance_m: number;
  visual_score?: number | null;
  temporal_score?: number | null;
  fused_score?: number | null;
  decision_id?: string | null;
}

export interface TrajectoryRead {
  vehicle_id: string;
  display_ref: string;
  canonical_plate?: string | null;
  points: TrajectoryPoint[];
  hops: TrajectoryHop[];
}

export interface SightingDetailRead extends Sighting {
  decisions: MatchDecision[];
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface HealthRead {
  status: string;
  index_size: number;
  camera_count: number;
}
