"""``match_decisions`` table (schema.md section 3.7) — the audit trail of reasoning.

Every candidate evaluated during resolution writes a row here — accepted,
rejected, and ambiguous alike. This is what makes the evidence panel and the
ablation study possible. ``rejection_reason`` carries the full enum: the four
spatio-temporal gate reasons plus the resolver-emitted BELOW_THRESHOLD,
AMBIGUOUS_MARGIN, OPERATOR_REJECTED and CLASS_MISMATCH.
"""
from typing import Optional

from sqlalchemy import CheckConstraint, Column, ForeignKey, Index, String, text
from sqlmodel import Field, SQLModel

from app.models.base import new_id, utcnow


class MatchDecision(SQLModel, table=True):
    __tablename__ = "match_decisions"
    __table_args__ = (
        CheckConstraint("tier IN ('plate','visual')", name="ck_decisions_tier"),
        CheckConstraint(
            "outcome IN ('accepted','rejected','ambiguous','superseded')",
            name="ck_decisions_outcome",
        ),
        CheckConstraint(
            "visual_score IS NULL OR visual_score BETWEEN -1 AND 1",
            name="ck_decisions_visual_score",
        ),
        CheckConstraint(
            "plate_score IS NULL OR plate_score BETWEEN 0 AND 1",
            name="ck_decisions_plate_score",
        ),
        CheckConstraint(
            "temporal_score IS NULL OR temporal_score BETWEEN 0 AND 1",
            name="ck_decisions_temporal_score",
        ),
        CheckConstraint(
            "fused_score IS NULL OR fused_score BETWEEN 0 AND 1",
            name="ck_decisions_fused_score",
        ),
        CheckConstraint("gate_passed IN (0,1)", name="ck_decisions_gate_passed"),
        CheckConstraint(
            "rejection_reason IS NULL OR rejection_reason IN "
            "('TEMPORAL_TOO_FAST','TEMPORAL_EXPIRED','NO_PATH','SAME_CAMERA_TOO_SOON',"
            "'BELOW_THRESHOLD','AMBIGUOUS_MARGIN','OPERATOR_REJECTED','CLASS_MISMATCH')",
            name="ck_decisions_rejection_reason",
        ),
        CheckConstraint(
            "review_status IN ('auto','confirmed','rejected')",
            name="ck_decisions_review_status",
        ),
        Index("idx_decisions_sighting", "sighting_id", text("fused_score DESC")),
        Index("idx_decisions_vehicle", "candidate_vehicle_id"),
        Index(
            "idx_decisions_review",
            "review_status",
            text("created_at DESC"),
            sqlite_where=text("review_status IN ('auto','confirmed')"),
        ),
        Index("idx_decisions_outcome", "outcome", text("created_at DESC")),
        Index(
            "idx_decisions_reason",
            "rejection_reason",
            sqlite_where=text("rejection_reason IS NOT NULL"),
        ),
    )

    id: str = Field(default_factory=new_id, primary_key=True)
    sighting_id: str = Field(
        sa_column=Column(
            String, ForeignKey("sightings.id", ondelete="CASCADE"), nullable=False
        )
    )
    candidate_vehicle_id: Optional[str] = Field(
        default=None,
        sa_column=Column(
            String, ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=True
        ),
    )
    candidate_sighting_id: Optional[str] = Field(
        default=None,
        sa_column=Column(
            String, ForeignKey("sightings.id", ondelete="SET NULL"), nullable=True
        ),
    )

    tier: str = Field(nullable=False)
    outcome: str = Field(nullable=False)

    visual_score: Optional[float] = Field(default=None)
    plate_score: Optional[float] = Field(default=None)
    temporal_score: Optional[float] = Field(default=None)
    fused_score: Optional[float] = Field(default=None)
    runner_up_score: Optional[float] = Field(default=None)

    gate_passed: bool = Field(default=False, nullable=False)
    rejection_reason: Optional[str] = Field(default=None)

    elapsed_seconds: Optional[int] = Field(default=None)
    min_transit_seconds: Optional[int] = Field(default=None)
    max_transit_seconds: Optional[int] = Field(default=None)
    path_distance_m: Optional[float] = Field(default=None)
    path_camera_codes: Optional[str] = Field(default=None)

    review_status: str = Field(default="auto", nullable=False)
    decided_by_user_id: Optional[str] = Field(
        default=None,
        sa_column=Column(
            String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
    )
    decided_at: Optional[str] = Field(default=None)

    created_at: str = Field(default_factory=utcnow, nullable=False)
