"""Identity resolution — the amended algorithm (techspec.md 5.6; TASK-211..214).

The core of the system. Given a new sighting, decide which known vehicle it
belongs to (or that it is a new one), and persist a MatchDecision for every
candidate evaluated so the evidence panel and the gate-on/gate-off ablation can
be reconstructed.

Amended visual tier: the spatio-temporal feasible set from the camera graph is
the candidate generator (NOT FAISS); visual similarity only scores and floors
within it, because the measured OSNet cosine distributions overlap.

Layering (rules.md 2): this service calls repositories and other services; it
issues no raw query itself. The one exception is that it adds MatchDecision rows
to the session directly — no match_decision_repo exists in the current scope; a
repository is the proper home for that write in the next session.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlmodel import Session

from app.core.config import get_settings
from app.models import MatchDecision, Sighting, Vehicle
from app.models.base import new_id, utcnow
from app.repositories import (
    camera_repo,
    match_decision_repo,
    sighting_repo,
    vehicle_repo,
)
from app.services import plate_matcher
from app.services.camera_graph import CameraGraph, CandidateSighting, FeasibleCandidate
from app.services.spatiotemporal_gate import GateDecision, GateStatus, evaluate_gate
from app.services.vector_index import VectorIndex, decode_embedding

# Outcome / tier / method / reason literals (schema.md 3.6, 3.7).
_TIER_PLATE = "plate"
_TIER_VISUAL = "visual"
_OUTCOME_ACCEPTED = "accepted"
_OUTCOME_REJECTED = "rejected"
_OUTCOME_AMBIGUOUS = "ambiguous"
_METHOD_PLATE_EXACT = "PLATE_EXACT"
_METHOD_PLATE_FUZZY = "PLATE_FUZZY"
_METHOD_VISUAL = "VISUAL"
_METHOD_NEW = "NEW"
_REASON_BELOW_THRESHOLD = "BELOW_THRESHOLD"
_REASON_AMBIGUOUS_MARGIN = "AMBIGUOUS_MARGIN"
_STATUS_MATCHED = "matched"
_STATUS_AMBIGUOUS = "ambiguous"
_STATUS_NEW = "new_vehicle"

_DISPLAY_REF_HEX_CHARS = 4
_TEMPORAL_MIN = 0.0
_TEMPORAL_MAX = 1.0
_DEFAULT_MISSING_COSINE = -1.0


@dataclass
class _Survivor:
    """A feasible candidate that cleared the visual floor, ready to rank."""

    vehicle_id: str
    candidate_sighting_id: str
    cosine: float
    temporal: float
    fused: float
    gate: GateDecision


def _parse_iso(value: str) -> datetime:
    """Parse an ISO-8601 UTC string (with a trailing Z) to a datetime."""
    return datetime.fromisoformat(value)


def _temporal_plausibility(gate: GateDecision) -> float:
    """1 - |elapsed - expected| / (max - min), clamped, expected = window midpoint."""
    if gate.min_transit_seconds is None or gate.max_transit_seconds is None:
        return _TEMPORAL_MAX
    spread = gate.max_transit_seconds - gate.min_transit_seconds
    if spread <= 0:
        return _TEMPORAL_MAX
    expected = (gate.min_transit_seconds + gate.max_transit_seconds) / 2
    raw = 1.0 - abs(gate.elapsed_seconds - expected) / spread
    return max(_TEMPORAL_MIN, min(_TEMPORAL_MAX, raw))


class IdentityResolver:
    """Resolves a sighting to a vehicle, recording every decision considered."""

    def __init__(
        self,
        session: Session,
        graph: CameraGraph,
        index: VectorIndex,
        *,
        gate_enabled: bool = True,
    ) -> None:
        self._session = session
        self._settings = get_settings()
        # Graph and index are injected and long-lived (built once at startup and
        # maintained incrementally by ingest); the resolver never rebuilds them.
        self._graph = graph
        self._index = index
        # gate_enabled=False bypasses the spatio-temporal gate entirely — the
        # gate-off arm of the ablation study (scripts/run_batch.py --no-gate).
        self._gate_enabled = gate_enabled
        self._decisions: list[MatchDecision] = []

    # -- decision persistence -------------------------------------------------

    def _record(self, sighting: Sighting, **fields: object) -> MatchDecision:
        if "visual_score" in fields and fields["visual_score"] is not None:
            fields["visual_score"] = max(-1.0, min(1.0, float(fields["visual_score"])))
        if "plate_score" in fields and fields["plate_score"] is not None:
            fields["plate_score"] = max(0.0, min(1.0, float(fields["plate_score"])))
        if "temporal_score" in fields and fields["temporal_score"] is not None:
            fields["temporal_score"] = max(0.0, min(1.0, float(fields["temporal_score"])))
        if "fused_score" in fields and fields["fused_score"] is not None:
            fields["fused_score"] = max(0.0, min(1.0, float(fields["fused_score"])))
        decision = MatchDecision(
            sighting_id=sighting.id, created_at=utcnow(), **fields  # type: ignore[arg-type]
        )
        # Persistence is deferred to match_decision_repo.create_many at the end of
        # resolve(), so this service issues no write itself (rules.md section 2).
        self._decisions.append(decision)
        return decision

    def _record_gate_fields(self, gate: GateDecision) -> dict[str, object]:
        codes = gate.path_camera_codes
        return {
            "gate_passed": gate.passed,
            "elapsed_seconds": gate.elapsed_seconds,
            "min_transit_seconds": gate.min_transit_seconds,
            "max_transit_seconds": gate.max_transit_seconds,
            "path_distance_m": gate.path_distance_m,
            "path_camera_codes": ",".join(codes) if codes else None,
        }

    # -- candidate loading ----------------------------------------------------

    def _candidate_reps(self, sighting: Sighting) -> list[Sighting]:
        """Latest embedded sighting per vehicle within the lookback window."""
        timestamp = _parse_iso(sighting.first_frame_at)
        since = timestamp - timedelta(
            seconds=self._settings.LOOKBACK_WINDOW_SECONDS
        )
        since_at = (
            since.isoformat(timespec="seconds").replace("+00:00", "Z")
        )
        reps = sighting_repo.get_latest_per_vehicle(self._session, since_at)
        return [rep for rep in reps if rep.vehicle_id != sighting.vehicle_id]

    def _gate_between(self, from_sighting: Sighting, to_sighting: Sighting) -> GateDecision:
        elapsed = int(
            (
                _parse_iso(to_sighting.first_frame_at)
                - _parse_iso(from_sighting.first_frame_at)
            ).total_seconds()
        )
        if not self._gate_enabled:
            return self._forced_pass(from_sighting, to_sighting, elapsed)
        return evaluate_gate(
            from_camera_id=from_sighting.camera_id,
            to_camera_id=to_sighting.camera_id,
            elapsed_seconds=elapsed,
            graph=self._graph,
            min_revisit_seconds=self._settings.MIN_REVISIT_SECONDS,
        )

    def _forced_pass(
        self, from_sighting: Sighting, to_sighting: Sighting, elapsed_seconds: int
    ) -> GateDecision:
        """A FEASIBLE decision ignoring timing — the gate-off ablation arm.

        The transit window is still read from the graph so the scoring temporal
        term and the evidence numbers are populated; only the accept/reject logic
        is bypassed.
        """
        path = self._graph.shortest_path(
            from_sighting.camera_id, to_sighting.camera_id
        )
        return GateDecision(
            status=GateStatus.FEASIBLE,
            passed=True,
            reason=None,
            elapsed_seconds=elapsed_seconds,
            min_transit_seconds=path.min_transit_seconds if path.exists else None,
            max_transit_seconds=path.max_transit_seconds if path.exists else None,
            path_distance_m=path.distance_m if path.exists else None,
            path_camera_codes=path.camera_codes if path.exists else None,
        )

    # -- tiers ----------------------------------------------------------------

    def _plate_tier(
        self, sighting: Sighting, reps: list[Sighting]
    ) -> Optional[str]:
        """Attempt a plate match. Returns the assigned vehicle_id, or None."""
        plate = sighting.plate_text_norm
        if not (sighting.plate_is_valid and plate):
            return None

        rep_by_vehicle = {rep.vehicle_id: rep for rep in reps}
        vehicles = vehicle_repo.get_by_ids(self._session, list(rep_by_vehicle.keys()))

        # Exact matches first, then confusion-map fuzzy matches.
        exact = [v for v in vehicles if v.canonical_plate == plate]
        fuzzy = [
            v
            for v in vehicles
            if v.canonical_plate
            and v.canonical_plate != plate
            and plate_matcher.is_confusable_match(plate, v.canonical_plate)
        ]

        for vehicle, method in (
            [(v, _METHOD_PLATE_EXACT) for v in exact]
            + [(v, _METHOD_PLATE_FUZZY) for v in fuzzy]
        ):
            rep = rep_by_vehicle[vehicle.id]
            gate = self._gate_between(rep, sighting)
            plate_score = plate_matcher.match_score(plate, vehicle.canonical_plate or "")
            if gate.passed:
                self._record(
                    sighting,
                    candidate_vehicle_id=vehicle.id,
                    candidate_sighting_id=rep.id,
                    tier=_TIER_PLATE,
                    outcome=_OUTCOME_ACCEPTED,
                    plate_score=plate_score,
                    **self._record_gate_fields(gate),
                )
                self._assign(sighting, vehicle.id, method, plate_score)
                return vehicle.id
            # Plate matched but the gate rejected: record and fall through.
            self._record(
                sighting,
                candidate_vehicle_id=vehicle.id,
                candidate_sighting_id=rep.id,
                tier=_TIER_PLATE,
                outcome=_OUTCOME_REJECTED,
                plate_score=plate_score,
                rejection_reason=gate.reason,
                **self._record_gate_fields(gate),
            )
        return None

    def _visual_tier(
        self, sighting: Sighting, reps: list[Sighting]
    ) -> Optional[str]:
        """Score the spatio-temporal feasible set. Returns assigned id, or None."""
        if sighting.embedding is None:
            return None
        query = decode_embedding(sighting.embedding, self._settings.EMBEDDING_DIM)
        rep_by_vehicle = {rep.vehicle_id: rep for rep in reps}
        cosine_by_sighting = self._index.search_subset(
            query, [rep.id for rep in reps]
        )

        if self._gate_enabled:
            feasible = self._graph.feasible_candidates(
                camera_id=sighting.camera_id,
                timestamp=_parse_iso(sighting.first_frame_at),
                last_sightings=[
                    CandidateSighting(
                        vehicle_id=rep.vehicle_id,  # type: ignore[arg-type]
                        camera_id=rep.camera_id,
                        seen_at=_parse_iso(rep.first_frame_at),
                    )
                    for rep in reps
                ],
                min_revisit_seconds=self._settings.MIN_REVISIT_SECONDS,
            )
        else:
            # Gate off: every candidate is "feasible" — no physics filter.
            feasible = [
                FeasibleCandidate(rep.vehicle_id, self._gate_between(rep, sighting))
                for rep in reps
            ]
        feasible_vehicle_ids = {fc.vehicle_id for fc in feasible}

        # Persist gate rejections for candidates that are NOT feasible, carrying
        # the visual score so the evidence panel can show "0.74 but too fast".
        for rep in reps:
            if rep.vehicle_id in feasible_vehicle_ids:
                continue
            gate = self._gate_between(rep, sighting)
            self._record(
                sighting,
                candidate_vehicle_id=rep.vehicle_id,
                candidate_sighting_id=rep.id,
                tier=_TIER_VISUAL,
                outcome=_OUTCOME_REJECTED,
                visual_score=cosine_by_sighting.get(rep.id, _DEFAULT_MISSING_COSINE),
                rejection_reason=gate.reason,
                **self._record_gate_fields(gate),
            )

        survivors = self._score_feasible(
            sighting, feasible, rep_by_vehicle, cosine_by_sighting
        )
        if not survivors:
            return None
        return self._assign_or_ambiguous(sighting, survivors)

    def _score_feasible(
        self,
        sighting: Sighting,
        feasible: list,
        rep_by_vehicle: dict,
        cosine_by_sighting: dict[str, float],
    ) -> list[_Survivor]:
        survivors: list[_Survivor] = []
        for fc in feasible:
            rep = rep_by_vehicle[fc.vehicle_id]
            gate = fc.decision
            cosine = cosine_by_sighting.get(rep.id, _DEFAULT_MISSING_COSINE)
            temporal = _temporal_plausibility(gate)
            if cosine < self._settings.VISUAL_FLOOR:
                self._record(
                    sighting,
                    candidate_vehicle_id=fc.vehicle_id,
                    candidate_sighting_id=rep.id,
                    tier=_TIER_VISUAL,
                    outcome=_OUTCOME_REJECTED,
                    visual_score=cosine,
                    temporal_score=temporal,
                    rejection_reason=_REASON_BELOW_THRESHOLD,
                    **self._record_gate_fields(gate),
                )
                continue
            fused = (
                self._settings.W_VISUAL * cosine
                + self._settings.W_TEMPORAL * temporal
            )
            survivors.append(
                _Survivor(fc.vehicle_id, rep.id, cosine, temporal, fused, gate)
            )
        survivors.sort(key=lambda s: s.fused, reverse=True)
        return survivors

    def _assign_or_ambiguous(
        self, sighting: Sighting, survivors: list[_Survivor]
    ) -> Optional[str]:
        top = survivors[0]
        runner_up = survivors[1].fused if len(survivors) > 1 else None

        if (
            len(survivors) > 1
            and (top.fused - survivors[1].fused) < self._settings.AMBIGUITY_MARGIN
        ):
            self._record(
                sighting,
                candidate_vehicle_id=top.vehicle_id,
                candidate_sighting_id=top.candidate_sighting_id,
                tier=_TIER_VISUAL,
                outcome=_OUTCOME_AMBIGUOUS,
                visual_score=top.cosine,
                temporal_score=top.temporal,
                fused_score=top.fused,
                runner_up_score=runner_up,
                rejection_reason=_REASON_AMBIGUOUS_MARGIN,
                **self._record_gate_fields(top.gate),
            )
            self._record_also_considered(sighting, survivors[1:])
            sighting.resolution_status = _STATUS_AMBIGUOUS
            self._session.add(sighting)
            return None

        self._record(
            sighting,
            candidate_vehicle_id=top.vehicle_id,
            candidate_sighting_id=top.candidate_sighting_id,
            tier=_TIER_VISUAL,
            outcome=_OUTCOME_ACCEPTED,
            visual_score=top.cosine,
            temporal_score=top.temporal,
            fused_score=top.fused,
            runner_up_score=runner_up,
            **self._record_gate_fields(top.gate),
        )
        self._record_also_considered(sighting, survivors[1:])
        self._assign(sighting, top.vehicle_id, _METHOD_VISUAL, top.fused)
        return top.vehicle_id

    def _record_also_considered(
        self, sighting: Sighting, others: list[_Survivor]
    ) -> None:
        """Record the lower-ranked survivors as considered-but-rejected."""
        for survivor in others:
            self._record(
                sighting,
                candidate_vehicle_id=survivor.vehicle_id,
                candidate_sighting_id=survivor.candidate_sighting_id,
                tier=_TIER_VISUAL,
                outcome=_OUTCOME_REJECTED,
                visual_score=survivor.cosine,
                temporal_score=survivor.temporal,
                fused_score=survivor.fused,
                **self._record_gate_fields(survivor.gate),
            )

    # -- assignment and counters ---------------------------------------------

    def _assign(
        self, sighting: Sighting, vehicle_id: str, method: str, score: Optional[float]
    ) -> None:
        sighting.vehicle_id = vehicle_id
        sighting.resolution_status = _STATUS_MATCHED
        sighting.match_method = method
        sighting.match_score = score
        self._session.add(sighting)
        self._refresh_counters(vehicle_id, sighting.first_frame_at)

    def _new_identity(self, sighting: Sighting) -> str:
        vehicle = Vehicle(
            id=new_id(),
            status="active",
            display_ref="",
            vehicle_class=sighting.vehicle_class,
            canonical_plate=sighting.plate_text_norm if sighting.plate_is_valid else None,
            plate_confidence=sighting.plate_confidence if sighting.plate_is_valid else None,
            plate_is_valid=sighting.plate_is_valid,
        )
        hex_chars = vehicle.id.replace("-", "")[:_DISPLAY_REF_HEX_CHARS].upper()
        vehicle.display_ref = f"#{hex_chars}"
        vehicle_repo.create(self._session, vehicle)
        sighting.vehicle_id = vehicle.id
        sighting.resolution_status = _STATUS_NEW
        sighting.match_method = _METHOD_NEW
        sighting.match_score = None
        self._session.add(sighting)
        self._refresh_counters(vehicle.id, sighting.first_frame_at)
        return vehicle.id

    def _refresh_counters(self, vehicle_id: str, fallback_first_frame_at: str) -> None:
        self._session.flush()
        sightings = sighting_repo.get_by_vehicle(self._session, vehicle_id)
        if sightings:
            frames = [s.first_frame_at for s in sightings]
            first_seen = min(frames)
            last_seen = max(frames)
            cameras = {s.camera_id for s in sightings}
        else:
            first_seen = last_seen = fallback_first_frame_at
            cameras = set()
        vehicle_repo.update_counters(
            self._session,
            vehicle_id,
            sighting_count=len(sightings),
            camera_count=len(cameras),
            last_seen_at=last_seen,
            first_seen_at=first_seen,
        )
        # Promote the best plate and class from sightings to the vehicle row.
        self._refresh_plate_and_class(vehicle_id, sightings)

    def _refresh_plate_and_class(
        self, vehicle_id: str, sightings: list
    ) -> None:
        vehicle = vehicle_repo.get_by_id(self._session, vehicle_id)
        if vehicle is None:
            return
        best_plate_sighting = max(
            (s for s in sightings if s.plate_is_valid and s.plate_text_norm),
            key=lambda s: s.plate_confidence or 0.0,
            default=None,
        )
        if best_plate_sighting is not None:
            vehicle.canonical_plate = best_plate_sighting.plate_text_norm
            vehicle.plate_confidence = best_plate_sighting.plate_confidence
            vehicle.plate_is_valid = True
        classes = [s.vehicle_class for s in sightings if s.vehicle_class]
        if classes:
            vehicle.vehicle_class = max(set(classes), key=classes.count)
        self._session.add(vehicle)
        self._session.flush()

    # -- entry point ----------------------------------------------------------

    def resolve(self, sighting: Sighting) -> tuple[Optional[str], list[MatchDecision]]:
        reps = self._candidate_reps(sighting)

        assigned = self._plate_tier(sighting, reps)
        if assigned is None:
            assigned = self._visual_tier(sighting, reps)
        # AMBIGUOUS is a deliberate non-assignment; it must not fall through to a
        # new identity. Only an empty/floored candidate set creates one.
        if assigned is None and sighting.resolution_status != _STATUS_AMBIGUOUS:
            assigned = self._new_identity(sighting)

        match_decision_repo.create_many(self._session, self._decisions)
        self._session.flush()
        return assigned, self._decisions


def build_graph(session: Session) -> CameraGraph:
    """Build the camera graph from the topology tables (once, at startup)."""
    cameras = camera_repo.get_all_cameras(session)
    edges = camera_repo.get_all_edges(session)
    return CameraGraph.from_models(cameras, edges)


def resolve(
    session: Session,
    sighting: Sighting,
    *,
    graph: Optional[CameraGraph] = None,
    index: Optional[VectorIndex] = None,
    gate_enabled: bool = True,
) -> tuple[Optional[str], list[MatchDecision]]:
    """Resolve a sighting to a vehicle (techspec.md 5.6).

    Args:
        session: the database session; new rows are flushed but not committed.
        sighting: the persisted sighting to resolve (with embedding and camera).
        graph: a prebuilt camera graph; built from the session if omitted.
        index: a long-lived vector index; built from the session if omitted.

    When ``graph`` and ``index`` are supplied (the ingest/batch path) nothing is
    rebuilt. When omitted (standalone/test use) they are constructed from the
    session for convenience.

    Returns:
        The assigned ``vehicle_id`` (never None once NEW runs) and the
        MatchDecision rows written for every candidate evaluated.
    """
    if graph is None:
        graph = build_graph(session)
    if index is None:
        index = VectorIndex(dim=get_settings().EMBEDDING_DIM)
        index.rebuild_from_db(session)
    return IdentityResolver(
        session, graph, index, gate_enabled=gate_enabled
    ).resolve(sighting)
