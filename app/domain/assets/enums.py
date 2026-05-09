from __future__ import annotations

from enum import StrEnum


class AssetType(StrEnum):
    MEAL_BOX = "meal_box"
    DRINK_CUP = "drink_cup"


class AssetStatus(StrEnum):
    MANUFACTURED = "manufactured"
    AT_CLEANING_CENTER = "at_cleaning_center"
    WASHING = "washing"
    CLEANED_READY = "cleaned_ready"
    IN_TRANSIT_TO_RESTAURANT = "in_transit_to_restaurant"
    AT_RESTAURANT = "at_restaurant"
    PICKED_BY_COURIER = "picked_by_courier"
    WITH_CONSUMER = "with_consumer"
    RETURN_PENDING_DEPOSIT = "return_pending_deposit"
    DEPOSITED_IN_RETURN_BOX = "deposited_in_return_box"
    COLLECTED_BY_RECYCLING_UNIT = "collected_by_recycling_unit"
    RETURNED_TO_CLEANING_CENTER = "returned_to_cleaning_center"
    UNDER_INSPECTION = "under_inspection"
    DAMAGED = "damaged"
    LOST = "lost"
    RETIRED = "retired"
    UNDER_DISPUTE = "under_dispute"


class HolderType(StrEnum):
    CLEANING_CENTER = "cleaning_center"
    RESTAURANT = "restaurant"
    COURIER = "courier"
    CONSUMER = "consumer"
    RETURN_BOX = "return_box"
    RECYCLER = "recycler"


class ActorRole(StrEnum):
    ADMIN = "admin"
    CLEANING_CENTER = "cleaning_center"
    RESTAURANT = "restaurant"
    COURIER = "courier"
    CONSUMER = "consumer"
    RECYCLER = "recycler"
    PARTNER = "partner"
    SUPPORT = "support"
    SYSTEM = "system"


TERMINAL_STATUSES = frozenset({AssetStatus.RETIRED})

ACTIVE_STATUSES = frozenset(s for s in AssetStatus if s not in TERMINAL_STATUSES)
