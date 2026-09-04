"""Seed the demo topology — 5 Patna cameras and 5 edges (schema.md section 6)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select

import app.db.session as db
from app.models import Camera, CameraEdge

CAMERAS = [
    ("CAM-01", "Dak Bungalow Chauraha", 25.6093, 85.1376),
    ("CAM-02", "Income Tax Golambar", 25.6138, 85.1322),
    ("CAM-03", "Gandhi Maidan Gate 1", 25.6205, 85.1441),
]

EDGES = [
    ("CAM-01", "CAM-02", 2150, 180, 1450, True),
    ("CAM-02", "CAM-03", 2800, 220, 1600, True),
    ("CAM-01", "CAM-03", 3400, 300, 2000, True),
]


def seed() -> None:
    db.init_db()
    with Session(db.engine) as session:
        existing = {c.code for c in session.exec(select(Camera)).all()}

        created_cameras = 0
        camera_by_code: dict[str, Camera] = {}
        for code, name, lat, lng in CAMERAS:
            if code in existing:
                cam = session.exec(select(Camera).where(Camera.code == code)).first()
                camera_by_code[code] = cam
                continue
            cam = Camera(code=code, name=name, latitude=lat, longitude=lng)
            session.add(cam)
            session.flush()
            camera_by_code[code] = cam
            created_cameras += 1

        created_edges = 0
        for from_code, to_code, dist, min_s, max_s, bidir in EDGES:
            from_cam = camera_by_code[from_code]
            to_cam = camera_by_code[to_code]
            exists = session.exec(
                select(CameraEdge).where(
                    CameraEdge.from_camera_id == from_cam.id,
                    CameraEdge.to_camera_id == to_cam.id,
                )
            ).first()
            if exists:
                continue
            edge = CameraEdge(
                from_camera_id=from_cam.id,
                to_camera_id=to_cam.id,
                distance_m=dist,
                min_transit_seconds=min_s,
                max_transit_seconds=max_s,
                is_bidirectional=bidir,
            )
            session.add(edge)
            created_edges += 1

        session.commit()
        print(f"Seeded {created_cameras} cameras, {created_edges} edges.")


if __name__ == "__main__":
    seed()
