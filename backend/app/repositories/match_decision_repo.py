"""Match-decision database access (rules.md section 2 layering).

Every decision the resolver reaches is persisted here — accepted, rejected and
ambiguous alike — so the evidence panel and the gate-on/gate-off ablation can be
reconstructed from the table rather than from logs.
"""
from collections.abc import Sequence

from sqlalchemy import func
from sqlmodel import Session, select

from app.models import MatchDecision

_OUTCOME_AMBIGUOUS = "ambiguous"


def create_many(
    session: Session, decisions: Sequence[MatchDecision]
) -> list[MatchDecision]:
    """Persist a batch of decisions and flush so ids are assigned."""
    session.add_all(decisions)
    session.flush()
    return list(decisions)


def get_by_sighting(session: Session, sighting_id: str) -> list[MatchDecision]:
    """Return every decision recorded for a sighting, best fused score first."""
    return list(
        session.exec(
            select(MatchDecision)
            .where(MatchDecision.sighting_id == sighting_id)
            .order_by(MatchDecision.fused_score.desc())  # type: ignore[union-attr]
        ).all()
    )


def get_ambiguous(session: Session) -> list[MatchDecision]:
    """Return the ambiguous decisions — the operator review queue."""
    return list(
        session.exec(
            select(MatchDecision)
            .where(MatchDecision.outcome == _OUTCOME_AMBIGUOUS)
            .order_by(MatchDecision.created_at.desc())  # type: ignore[union-attr]
        ).all()
    )


def count_by_rejection_reason(session: Session) -> dict[str, int]:
    """Count decisions grouped by rejection reason (the ablation study).

    Only rows that carry a reason are counted, so the result maps each reason to
    the number of times the resolver refused a match for it.
    """
    rows = session.exec(
        select(MatchDecision.rejection_reason, func.count())
        .where(MatchDecision.rejection_reason.is_not(None))  # type: ignore[union-attr]
        .group_by(MatchDecision.rejection_reason)
    ).all()
    return {reason: count for reason, count in rows}
