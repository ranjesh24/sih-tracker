"""Reset demo state between runs (techspec.md 5.4 /system/reset-demo, offline form).

Deletes sightings, vehicles, match_decisions and crop files; keeps cameras,
edges and users. A running server rebuilds its in-memory index from the (now
empty) sightings table on next startup, so the index is cleared implicitly.

Usage:
    python scripts/reset_demo.py
"""
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from sqlalchemy import delete  # noqa: E402
from sqlmodel import Session  # noqa: E402

import app.db.session as db_session  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.models import MatchDecision, Sighting, Vehicle, Video  # noqa: E402


def _clear_crops(crop_dir: Path) -> int:
    """Delete crop files under the storage path. Returns the count removed."""
    if not crop_dir.is_dir():
        return 0
    removed = 0
    for path in crop_dir.rglob("*"):
        if path.is_file():
            path.unlink()
            removed += 1
    return removed


def reset() -> dict:
    """Wipe transient demo data, keep topology and users."""
    db_session.init_db()
    with Session(db_session.engine) as session:
        # match_decisions first (FK to sightings/vehicles), then sightings, then
        # vehicles. Explicit order keeps it correct even if FKs were off.
        session.execute(delete(MatchDecision))
        session.execute(delete(Sighting))
        session.execute(delete(Vehicle))
        # Videos too: otherwise the live wall keeps showing tiles for cameras
        # whose footage and sightings have just been wiped.
        session.execute(delete(Video))
        session.commit()
    crops_removed = _clear_crops(Path(get_settings().CROP_STORAGE_PATH))
    return {
        "cleared": ["match_decisions", "sightings", "vehicles", "videos"],
        "crops_removed": crops_removed,
    }


def main() -> None:
    summary = reset()
    print("Reset complete. Kept cameras, edges and users.")
    print(f"Cleared tables : {', '.join(summary['cleared'])}")
    print(f"Crop files removed: {summary['crops_removed']}")


if __name__ == "__main__":
    main()
