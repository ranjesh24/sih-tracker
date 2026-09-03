"""Batch resolver — how the demo actually runs (no HTTP, no workers).

Reads sighting JSON records from a directory of ``*.json`` files or a ``.jsonl``
file, sorts them by ``first_frame_at`` across all cameras, and resolves them in
order through the same code path as ingest. ``--no-gate`` bypasses the
spatio-temporal gate entirely; running with and without it on the same input is
the ablation study.

Usage:
    python scripts/run_batch.py data/sightings.jsonl
    python scripts/run_batch.py data/sightings.jsonl --no-gate
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from sqlmodel import Session  # noqa: E402

import app.db.session as db_session  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.schemas.ingest import IngestSighting  # noqa: E402
from app.services.identity_resolver import build_graph  # noqa: E402
from app.services.ingest_service import ingest_one  # noqa: E402
from app.services.vector_index import VectorIndex  # noqa: E402

_METHOD_NEW = "NEW"
_STATUS_AMBIGUOUS = "ambiguous"
_AMBIGUOUS_MARGIN = "AMBIGUOUS_MARGIN"


def _load_records(input_path: Path) -> list[IngestSighting]:
    """Load sighting records from a .jsonl file or a directory of .json files."""
    raw: list[dict] = []
    if input_path.is_dir():
        for json_file in sorted(input_path.glob("*.json")):
            content = json.loads(json_file.read_text())
            raw.extend(content if isinstance(content, list) else [content])
    elif input_path.suffix == ".jsonl":
        for line in input_path.read_text().splitlines():
            line = line.strip()
            if line:
                raw.append(json.loads(line))
    else:
        content = json.loads(input_path.read_text())
        raw = content if isinstance(content, list) else [content]

    records = [IngestSighting.model_validate(item) for item in raw]
    records.sort(key=lambda record: record.first_frame_at)
    return records


def run(input_path: Path, gate_enabled: bool) -> dict:
    """Resolve every record in order and return a summary dict."""
    db_session.init_db()
    settings = get_settings()

    method_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    ambiguous_count = 0
    total = 0

    with Session(db_session.engine) as session:
        graph = build_graph(session)
        index = VectorIndex(dim=settings.EMBEDDING_DIM)
        index.rebuild_from_db(session)

        for record in _load_records(input_path):
            outcome = ingest_one(
                session, record, graph, index, gate_enabled=gate_enabled
            )
            session.commit()
            total += 1
            if outcome.sighting.resolution_status == _STATUS_AMBIGUOUS:
                ambiguous_count += 1
            if outcome.sighting.match_method is not None:
                method_counts[outcome.sighting.match_method] += 1
            for decision in outcome.decisions:
                if decision.rejection_reason is not None:
                    reason_counts[decision.rejection_reason] += 1

    return {
        "gate_enabled": gate_enabled,
        "total_sightings": total,
        "vehicles_created": method_counts.get(_METHOD_NEW, 0),
        "matches_by_method": dict(method_counts),
        "rejections_by_reason": dict(reason_counts),
        "ambiguous_margin_count": reason_counts.get(_AMBIGUOUS_MARGIN, 0),
    }


def _print_summary(summary: dict) -> None:
    print("=" * 52)
    print(f"Batch complete  (gate {'ON' if summary['gate_enabled'] else 'OFF'})")
    print("=" * 52)
    print(f"total sightings      : {summary['total_sightings']}")
    print(f"vehicles created     : {summary['vehicles_created']}")
    print("matches by method    :")
    for method, count in sorted(summary["matches_by_method"].items()):
        print(f"    {method:<14} {count}")
    print("rejections by reason :")
    for reason, count in sorted(summary["rejections_by_reason"].items()):
        print(f"    {reason:<20} {count}")
    print(f"AMBIGUOUS_MARGIN     : {summary['ambiguous_margin_count']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch resolver / ablation runner")
    parser.add_argument("input", type=Path, help="JSONL file or directory of JSON")
    parser.add_argument(
        "--no-gate",
        action="store_true",
        help="Bypass the spatio-temporal gate (ablation: gate-off arm)",
    )
    args = parser.parse_args()
    summary = run(args.input, gate_enabled=not args.no_gate)
    _print_summary(summary)


if __name__ == "__main__":
    main()
