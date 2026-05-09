"""Asset state machine.

Centralizes legal status transitions and the actor roles allowed to trigger
them. The route layer must NEVER mutate ``Asset.status`` directly; it must go
through :class:`StateMachine.transition` so that:

* illegal transitions raise immediately
* role-based authorization is uniform
* downstream services (audit, hash chain) can be wired in one place
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.assets.enums import (
    ACTIVE_STATUSES,
    ActorRole,
    AssetStatus,
)


class IllegalStateTransition(Exception):
    """Raised when a transition is not declared in the legal map."""


class UnauthorizedTransition(Exception):
    """Raised when the actor's role cannot trigger a legal transition."""


@dataclass(frozen=True)
class Transition:
    src: AssetStatus
    dst: AssetStatus
    allowed_roles: frozenset[ActorRole]


def _t(src: AssetStatus, dst: AssetStatus, *roles: ActorRole) -> Transition:
    return Transition(src=src, dst=dst, allowed_roles=frozenset(roles))


_HAPPY_PATH: tuple[Transition, ...] = (
    _t(AssetStatus.MANUFACTURED, AssetStatus.AT_CLEANING_CENTER, ActorRole.CLEANING_CENTER),
    _t(AssetStatus.AT_CLEANING_CENTER, AssetStatus.WASHING, ActorRole.CLEANING_CENTER),
    _t(AssetStatus.WASHING, AssetStatus.CLEANED_READY, ActorRole.CLEANING_CENTER),
    _t(
        AssetStatus.CLEANED_READY,
        AssetStatus.IN_TRANSIT_TO_RESTAURANT,
        ActorRole.CLEANING_CENTER,
    ),
    _t(
        AssetStatus.IN_TRANSIT_TO_RESTAURANT,
        AssetStatus.AT_RESTAURANT,
        ActorRole.RESTAURANT,
    ),
    _t(AssetStatus.AT_RESTAURANT, AssetStatus.PICKED_BY_COURIER, ActorRole.COURIER),
    _t(AssetStatus.PICKED_BY_COURIER, AssetStatus.WITH_CONSUMER, ActorRole.COURIER),
    _t(
        AssetStatus.WITH_CONSUMER,
        AssetStatus.RETURN_PENDING_DEPOSIT,
        ActorRole.CONSUMER,
    ),
    _t(
        AssetStatus.RETURN_PENDING_DEPOSIT,
        AssetStatus.DEPOSITED_IN_RETURN_BOX,
        ActorRole.SYSTEM,
    ),
    _t(
        AssetStatus.DEPOSITED_IN_RETURN_BOX,
        AssetStatus.COLLECTED_BY_RECYCLING_UNIT,
        ActorRole.RECYCLER,
    ),
    _t(
        AssetStatus.COLLECTED_BY_RECYCLING_UNIT,
        AssetStatus.RETURNED_TO_CLEANING_CENTER,
        ActorRole.CLEANING_CENTER,
    ),
    # Consumer may also drop directly at the cleaning center (skipping recycler).
    _t(
        AssetStatus.DEPOSITED_IN_RETURN_BOX,
        AssetStatus.RETURNED_TO_CLEANING_CENTER,
        ActorRole.CLEANING_CENTER,
    ),
    _t(
        AssetStatus.RETURNED_TO_CLEANING_CENTER,
        AssetStatus.UNDER_INSPECTION,
        ActorRole.CLEANING_CENTER,
    ),
    _t(AssetStatus.UNDER_INSPECTION, AssetStatus.WASHING, ActorRole.CLEANING_CENTER),
    _t(AssetStatus.UNDER_INSPECTION, AssetStatus.DAMAGED, ActorRole.CLEANING_CENTER),
    _t(AssetStatus.UNDER_INSPECTION, AssetStatus.RETIRED, ActorRole.CLEANING_CENTER),
)


_EXCEPTIONS: tuple[Transition, ...] = (
    _t(AssetStatus.DAMAGED, AssetStatus.RETIRED, ActorRole.CLEANING_CENTER, ActorRole.ADMIN),
    _t(
        AssetStatus.LOST,
        AssetStatus.RETURNED_TO_CLEANING_CENTER,
        ActorRole.CLEANING_CENTER,
        ActorRole.SUPPORT,
    ),
    _t(
        AssetStatus.UNDER_DISPUTE,
        AssetStatus.UNDER_INSPECTION,
        ActorRole.SUPPORT,
        ActorRole.ADMIN,
    ),
)


def _build_universal_transitions() -> tuple[Transition, ...]:
    universal: list[Transition] = []
    for src in ACTIVE_STATUSES:
        if src in {AssetStatus.LOST, AssetStatus.UNDER_DISPUTE}:
            continue
        universal.append(_t(src, AssetStatus.UNDER_DISPUTE, ActorRole.SUPPORT, ActorRole.ADMIN))
        universal.append(
            _t(src, AssetStatus.LOST, ActorRole.SUPPORT, ActorRole.ADMIN, ActorRole.CLEANING_CENTER)
        )
    return tuple(universal)


_TRANSITIONS: tuple[Transition, ...] = _HAPPY_PATH + _EXCEPTIONS + _build_universal_transitions()

_INDEX: dict[tuple[AssetStatus, AssetStatus], Transition] = {
    (t.src, t.dst): t for t in _TRANSITIONS
}


def is_legal(src: AssetStatus, dst: AssetStatus) -> bool:
    return (src, dst) in _INDEX


def allowed_roles(src: AssetStatus, dst: AssetStatus) -> frozenset[ActorRole]:
    transition = _INDEX.get((src, dst))
    if transition is None:
        return frozenset()
    return transition.allowed_roles


def assert_transition(src: AssetStatus, dst: AssetStatus, actor_role: ActorRole) -> None:
    transition = _INDEX.get((src, dst))
    if transition is None:
        raise IllegalStateTransition(f"{src} -> {dst} is not a legal transition")
    if actor_role not in transition.allowed_roles:
        raise UnauthorizedTransition(
            f"role {actor_role} cannot drive {src} -> {dst}; "
            f"allowed: {sorted(r.value for r in transition.allowed_roles)}"
        )


def legal_next_states(src: AssetStatus) -> frozenset[AssetStatus]:
    return frozenset(t.dst for t in _TRANSITIONS if t.src == src)
