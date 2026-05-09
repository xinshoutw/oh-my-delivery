from itertools import pairwise

import pytest
from app.domain.assets.enums import ActorRole, AssetStatus
from app.domain.assets.state_machine import (
    IllegalStateTransition,
    UnauthorizedTransition,
    assert_transition,
    is_legal,
    legal_next_states,
)


def test_happy_path_full_cycle_is_legal():
    chain = [
        AssetStatus.MANUFACTURED,
        AssetStatus.AT_CLEANING_CENTER,
        AssetStatus.WASHING,
        AssetStatus.CLEANED_READY,
        AssetStatus.IN_TRANSIT_TO_RESTAURANT,
        AssetStatus.AT_RESTAURANT,
        AssetStatus.PICKED_BY_COURIER,
        AssetStatus.WITH_CONSUMER,
        AssetStatus.RETURN_PENDING_DEPOSIT,
        AssetStatus.DEPOSITED_IN_RETURN_BOX,
        AssetStatus.COLLECTED_BY_RECYCLING_UNIT,
        AssetStatus.RETURNED_TO_CLEANING_CENTER,
        AssetStatus.UNDER_INSPECTION,
        AssetStatus.WASHING,
        AssetStatus.CLEANED_READY,
    ]
    for src, dst in pairwise(chain):
        assert is_legal(src, dst), f"{src} -> {dst} should be legal"


def test_courier_can_drive_pickup_but_consumer_cannot():
    assert_transition(
        AssetStatus.AT_RESTAURANT,
        AssetStatus.PICKED_BY_COURIER,
        ActorRole.COURIER,
    )
    with pytest.raises(UnauthorizedTransition):
        assert_transition(
            AssetStatus.AT_RESTAURANT,
            AssetStatus.PICKED_BY_COURIER,
            ActorRole.CONSUMER,
        )


def test_illegal_jump_raises():
    with pytest.raises(IllegalStateTransition):
        assert_transition(
            AssetStatus.AT_RESTAURANT,
            AssetStatus.WITH_CONSUMER,
            ActorRole.COURIER,
        )


def test_terminal_retired_has_no_outgoing_transitions():
    assert legal_next_states(AssetStatus.RETIRED) == frozenset()


def test_dispute_can_reach_inspection():
    assert is_legal(AssetStatus.UNDER_DISPUTE, AssetStatus.UNDER_INSPECTION)


def test_lost_can_be_recovered_to_cleaning_center():
    assert is_legal(AssetStatus.LOST, AssetStatus.RETURNED_TO_CLEANING_CENTER)


def test_any_active_can_be_marked_disputed_by_support():
    assert_transition(
        AssetStatus.WITH_CONSUMER,
        AssetStatus.UNDER_DISPUTE,
        ActorRole.SUPPORT,
    )
    assert_transition(
        AssetStatus.AT_RESTAURANT,
        AssetStatus.UNDER_DISPUTE,
        ActorRole.SUPPORT,
    )


def test_any_active_can_be_marked_lost_by_support():
    assert_transition(
        AssetStatus.WITH_CONSUMER,
        AssetStatus.LOST,
        ActorRole.SUPPORT,
    )


def test_consumer_cannot_mark_lost():
    with pytest.raises(UnauthorizedTransition):
        assert_transition(
            AssetStatus.WITH_CONSUMER,
            AssetStatus.LOST,
            ActorRole.CONSUMER,
        )


def test_consumer_drives_return_scan():
    assert_transition(
        AssetStatus.WITH_CONSUMER,
        AssetStatus.RETURN_PENDING_DEPOSIT,
        ActorRole.CONSUMER,
    )


def test_micro_switch_event_is_system_driven():
    assert_transition(
        AssetStatus.RETURN_PENDING_DEPOSIT,
        AssetStatus.DEPOSITED_IN_RETURN_BOX,
        ActorRole.SYSTEM,
    )


def test_consumer_cannot_drive_box_deposit_directly():
    with pytest.raises(UnauthorizedTransition):
        assert_transition(
            AssetStatus.RETURN_PENDING_DEPOSIT,
            AssetStatus.DEPOSITED_IN_RETURN_BOX,
            ActorRole.CONSUMER,
        )


def test_returned_box_can_be_collected_or_returned_directly_to_center():
    assert AssetStatus.COLLECTED_BY_RECYCLING_UNIT in legal_next_states(
        AssetStatus.DEPOSITED_IN_RETURN_BOX
    )
    assert AssetStatus.RETURNED_TO_CLEANING_CENTER in legal_next_states(
        AssetStatus.DEPOSITED_IN_RETURN_BOX
    )
