"""Model-neutral refresh-family state decisions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class RefreshDecisionCode(StrEnum):
    ACTIVE = "active"
    FAMILY_REVOKED = "family_revoked"
    FAMILY_EXPIRED = "family_expired"
    MEMBER_CONSUMED = "member_consumed"
    BINDING_MISMATCH = "binding_mismatch"


@dataclass(frozen=True)
class RefreshDecision:
    code: RefreshDecisionCode
    allowed: bool
    revoke_family: bool
    replay: bool = False


def decide_refresh(
    *,
    now: datetime,
    family_expires_at: datetime,
    family_revoked_at: datetime | None,
    member_consumed_at: datetime | None,
    binding_matches: bool,
) -> RefreshDecision:
    if family_revoked_at is not None:
        return RefreshDecision(RefreshDecisionCode.FAMILY_REVOKED, False, True)
    if family_expires_at <= now:
        return RefreshDecision(RefreshDecisionCode.FAMILY_EXPIRED, False, True)
    if member_consumed_at is not None:
        return RefreshDecision(RefreshDecisionCode.MEMBER_CONSUMED, False, True, replay=True)
    if not binding_matches:
        return RefreshDecision(RefreshDecisionCode.BINDING_MISMATCH, False, True)
    return RefreshDecision(RefreshDecisionCode.ACTIVE, True, False)
