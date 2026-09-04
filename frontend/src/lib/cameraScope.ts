/* cameraScope.ts — the single set of rules for "which cameras count".
 *
 * Live Wall, Trajectory Map and Evidence Panel all narrow to the same array:
 * the cameras with an uploaded video in the current batch, fetched once in
 * App.tsx. Everything here operates on that array so the three pages can never
 * disagree about which cameras, markers, tabs or counts exist.
 */
import type { Camera, TrajectoryPoint } from '../types/api';

/** Ordered Patna junctions used to place cameras that carry no coordinates.
 *  Seeded CAM-01..03 keep their own real coordinates and never reach this list;
 *  it exists so an operator-added camera is still placeable on the map. Far
 *  longer than any demo needs, so assignment never runs out of slots. */
export const PATNA_JUNCTIONS: { name: string; lat: number; lng: number }[] = [
  { name: 'Dak Bungalow Chauraha', lat: 25.6093, lng: 85.1376 },
  { name: 'Income Tax Golambar', lat: 25.6138, lng: 85.1322 },
  { name: 'Gandhi Maidan Gate 1', lat: 25.6205, lng: 85.1441 },
  { name: 'Kargil Chowk', lat: 25.6231, lng: 85.1387 },
  { name: 'Ashok Rajpath Crossing', lat: 25.6178, lng: 85.1712 },
  { name: 'Patna Junction Approach', lat: 25.6018, lng: 85.1372 },
  { name: 'Bailey Road Hartali Mor', lat: 25.6112, lng: 85.1063 },
  { name: 'Boring Road Chauraha', lat: 25.6154, lng: 85.1198 },
  { name: 'Rajendra Nagar Terminal', lat: 25.6041, lng: 85.1622 },
  { name: 'Kankarbagh Main Road', lat: 25.5921, lng: 85.1583 },
  { name: 'Chiraiyatand Bridge', lat: 25.6001, lng: 85.1497 },
  { name: 'Exhibition Road Crossing', lat: 25.6134, lng: 85.1435 },
  { name: 'Fraser Road Junction', lat: 25.6119, lng: 85.1401 },
  { name: 'Patliputra Golambar', lat: 25.6252, lng: 85.1094 },
  { name: 'Rukanpura Crossing', lat: 25.6087, lng: 85.0876 },
  { name: 'Danapur Cantonment', lat: 25.6349, lng: 85.0472 },
  { name: 'Gola Road Junction', lat: 25.6213, lng: 85.0721 },
  { name: 'Saguna Mor', lat: 25.6157, lng: 85.0618 },
  { name: 'Anisabad Golambar', lat: 25.5784, lng: 85.1216 },
  { name: 'Mithapur Bus Stand', lat: 25.5893, lng: 85.1338 },
  { name: 'Agam Kuan Crossing', lat: 25.6046, lng: 85.1789 },
  { name: 'Bhootnath Road Mor', lat: 25.5967, lng: 85.1704 },
  { name: 'NIT Patna Gate', lat: 25.6203, lng: 85.1739 },
  { name: 'Gaighat Ganga Path', lat: 25.6291, lng: 85.1652 },
];

/** Stable hash of a camera code. Same code always yields the same number, so a
 *  camera keeps its map position across reloads and across page navigations. */
function hashCode(value: string): number {
  let hash = 0;
  for (let i = 0; i < value.length; i += 1) {
    hash = (hash << 5) - hash + value.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash);
}

export type PlacedCamera = Camera & { lat: number; lng: number };

function hasCoordinates(camera: Camera): boolean {
  return (
    typeof camera.latitude === 'number' &&
    typeof camera.longitude === 'number' &&
    Number.isFinite(camera.latitude) &&
    Number.isFinite(camera.longitude) &&
    !(camera.latitude === 0 && camera.longitude === 0)
  );
}

/** Give every camera a position: its own if it has one, otherwise a junction
 *  assigned deterministically from its code. Collisions within the supplied set
 *  are resolved by probing forward, so two cameras never stack on one point. */
export function placeCameras(cameras: Camera[]): PlacedCamera[] {
  const taken = new Set<number>();

  // Cameras with real coordinates are placed first so they always win their
  // spot; only the remainder consume junction slots.
  const ordered = [...cameras].sort((a, b) => {
    const aHas = hasCoordinates(a) ? 0 : 1;
    const bHas = hasCoordinates(b) ? 0 : 1;
    return aHas - bHas || a.code.localeCompare(b.code);
  });

  return ordered.map((camera) => {
    if (hasCoordinates(camera)) {
      return { ...camera, lat: camera.latitude, lng: camera.longitude };
    }
    let slot = hashCode(camera.code) % PATNA_JUNCTIONS.length;
    let probes = 0;
    while (taken.has(slot) && probes < PATNA_JUNCTIONS.length) {
      slot = (slot + 1) % PATNA_JUNCTIONS.length;
      probes += 1;
    }
    taken.add(slot);
    const junction = PATNA_JUNCTIONS[slot];
    return { ...camera, lat: junction.lat, lng: junction.lng };
  });
}

/** Camera codes that currently have an uploaded video. */
export function scopedCodes(cameras: Camera[]): Set<string> {
  return new Set(cameras.map((camera) => camera.code));
}

/** Keep only the trajectory points recorded at a camera that has video, in
 *  timestamp order. A sighting at a camera with no uploaded video is dropped
 *  rather than drawn as a dead marker or a dead tab. */
export function scopePoints(
  points: TrajectoryPoint[],
  cameras: Camera[]
): TrajectoryPoint[] {
  // Zero uploads is the one case where scoping is skipped: there is nothing to
  // scope to, and the demo is expected to show its seeded/mock path rather than
  // a blank map. As soon as one video exists, filtering applies strictly.
  if (cameras.length === 0) {
    return [...points].sort((a, b) => a.timestamp.localeCompare(b.timestamp));
  }
  const codes = scopedCodes(cameras);
  return points
    .filter((point) => point.camera_code && codes.has(point.camera_code))
    .sort((a, b) => a.timestamp.localeCompare(b.timestamp));
}

/** Attach coordinates to scoped points, dropping any that cannot be placed. */
export function placePoints(
  points: TrajectoryPoint[],
  cameras: Camera[]
): (TrajectoryPoint & { lat: number; lng: number })[] {
  const placedByCode = new Map(
    placeCameras(cameras).map((camera) => [camera.code, camera])
  );
  return points.flatMap((point) => {
    const placed = point.camera_code ? placedByCode.get(point.camera_code) : undefined;
    if (placed) return [{ ...point, lat: placed.lat, lng: placed.lng }];
    // No matching camera in scope (the zero-upload case): fall back to the
    // coordinates the point already carries, so the path still draws.
    if (typeof point.lat === 'number' && typeof point.lng === 'number') {
      return [{ ...point, lat: point.lat, lng: point.lng }];
    }
    return [];
  });
}
