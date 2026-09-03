"""Match-decision response schema (schema.md 3.7)."""
from typing import Optional

from pydantic import BaseModel

from app.models import MatchDecision


class MatchDecisionRead(BaseModel):
    """A single decision considered during resolution — the evidence row."""

    id: str
    sighting_id: str
    candidate_vehicle_id: Optional[str]
    candidate_sighting_id: Optional[str]
    tier: str
    outcome: str
    visual_score: Optional[float]
    plate_score: Optional[float]
    temporal_score: Optional[float]
    fused_score: Optional[float]
    runner_up_score: Optional[float]
    gate_passed: bool
    rejection_reason: Optional[str]
    elapsed_seconds: Optional[int]
    min_transit_seconds: Optional[int]
    max_transit_seconds: Optional[int]
    path_distance_m: Optional[float]
    path_camera_codes: Optional[list[str]]
    created_at: str

    @classmethod
    def from_model(cls, decision: MatchDecision) -> "MatchDecisionRead":
        codes = (
            decision.path_camera_codes.split(",")
            if decision.path_camera_codes
            else None
        )
        return cls(
            id=decision.id,
            sighting_id=decision.sighting_id,
            candidate_vehicle_id=decision.candidate_vehicle_id,
            candidate_sighting_id=decision.candidate_sighting_id,
            tier=decision.tier,
            outcome=decision.outcome,
            visual_score=decision.visual_score,
            plate_score=decision.plate_score,
            temporal_score=decision.temporal_score,
            fused_score=decision.fused_score,
            runner_up_score=decision.runner_up_score,
            gate_passed=decision.gate_passed,
            rejection_reason=decision.rejection_reason,
            elapsed_seconds=decision.elapsed_seconds,
            min_transit_seconds=decision.min_transit_seconds,
            max_transit_seconds=decision.max_transit_seconds,
            path_distance_m=decision.path_distance_m,
            path_camera_codes=codes,
            created_at=decision.created_at,
        )
