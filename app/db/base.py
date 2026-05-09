"""SQLModel base + naming convention for predictable migrations."""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlmodel import SQLModel

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)
SQLModel.metadata.naming_convention = NAMING_CONVENTION  # type: ignore[attr-defined]


def import_all_models() -> None:
    """Import every SQLModel module so Alembic sees them.

    Migrations rely on ``SQLModel.metadata`` being populated, which only
    happens when each model module is imported.
    """
    from app.domain.assets import models as _assets  # noqa: F401
    from app.domain.audit import models as _audit  # noqa: F401
    from app.domain.consumers import models as _consumers  # noqa: F401
    from app.domain.delivery import models as _delivery  # noqa: F401
    from app.domain.deposits import models as _deposits  # noqa: F401
    from app.domain.devices import models as _devices  # noqa: F401
    from app.domain.dispatches import models as _dispatches  # noqa: F401
    from app.domain.hashchain import anchor_models as _anchor  # noqa: F401
    from app.domain.notifications import models as _notifications  # noqa: F401
    from app.domain.orders import models as _orders  # noqa: F401
    from app.domain.orders import order_assets as _order_assets  # noqa: F401
    from app.domain.partners import models as _partners  # noqa: F401
    from app.domain.pickup import models as _pickup  # noqa: F401
    from app.domain.returns import models as _returns  # noqa: F401
    from app.domain.rewards import models as _rewards  # noqa: F401
    from app.domain.washing import models as _washing  # noqa: F401
