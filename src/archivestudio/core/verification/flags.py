"""Persistence helpers for verification flag review decisions."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from archivestudio.core.models import (
    VERIFICATION_FLAG_STATUSES,
    VERIFICATION_STATUS_ACCEPTED_ALTERNATIVE,
    VERIFICATION_STATUS_MANUAL_EDIT,
    VERIFICATION_STATUS_OPEN,
    VERIFICATION_STATUS_STALE,
    VerificationFlag,
)


def load_open_verification_flags(
    session: Session,
    *,
    page_id: str,
    source_text_version_id: str,
) -> list[VerificationFlag]:
    """Return open review flags for the current text version."""
    return list(
        session.execute(
            select(VerificationFlag)
            .where(
                VerificationFlag.page_id == page_id,
                VerificationFlag.source_text_version_id == source_text_version_id,
                VerificationFlag.status == VERIFICATION_STATUS_OPEN,
            )
            .order_by(VerificationFlag.primary_start, VerificationFlag.created_at)
        ).scalars()
    )


def mark_verification_flag_decision(
    session: Session,
    *,
    flag_id: str,
    status: str,
    decided_by: str = "user",
) -> VerificationFlag:
    """Mark one verification flag as reviewed by a human."""
    if status not in VERIFICATION_FLAG_STATUSES:
        raise ValueError(f"Unsupported verification flag status: {status}")
    flag = session.get(VerificationFlag, flag_id)
    if flag is None:
        raise ValueError(f"Unknown verification flag: {flag_id}")
    flag.status = status
    flag.decided_at = datetime.now(timezone.utc)
    flag.decided_by = decided_by
    return flag


def link_decided_flags_to_text_version(
    session: Session,
    *,
    source_text_version_id: str,
    resulting_text_version_id: str,
) -> None:
    """Link accepted/manual decisions to the manual text version created by save."""
    flags = session.execute(
        select(VerificationFlag).where(
            VerificationFlag.source_text_version_id == source_text_version_id,
            VerificationFlag.resulting_text_version_id.is_(None),
            VerificationFlag.status.in_(
                [
                    VERIFICATION_STATUS_ACCEPTED_ALTERNATIVE,
                    VERIFICATION_STATUS_MANUAL_EDIT,
                ]
            ),
        )
    ).scalars()
    for flag in flags:
        flag.resulting_text_version_id = resulting_text_version_id


def apply_pending_verification_decisions(
    session: Session,
    *,
    source_text_version_id: str,
    decisions: dict[str, str],
    resulting_text_version_id: str,
) -> None:
    """Persist UI-pending accepted/manual decisions when text is actually saved."""
    for flag_id, status in decisions.items():
        if status not in {
            VERIFICATION_STATUS_ACCEPTED_ALTERNATIVE,
            VERIFICATION_STATUS_MANUAL_EDIT,
        }:
            continue
        flag = session.get(VerificationFlag, flag_id)
        if flag is None:
            continue
        if flag.source_text_version_id != source_text_version_id:
            continue
        if flag.status != VERIFICATION_STATUS_OPEN:
            continue
        flag.status = status
        flag.decided_at = datetime.now(timezone.utc)
        flag.decided_by = "user"
        flag.resulting_text_version_id = resulting_text_version_id


def mark_open_verification_flags_stale(
    session: Session,
    *,
    source_text_version_id: str,
) -> int:
    """Mark unresolved flags stale after their source text version is replaced."""
    flags = session.execute(
        select(VerificationFlag).where(
            VerificationFlag.source_text_version_id == source_text_version_id,
            VerificationFlag.status == VERIFICATION_STATUS_OPEN,
        )
    ).scalars()
    changed = 0
    for flag in flags:
        flag.status = VERIFICATION_STATUS_STALE
        changed += 1
    return changed
