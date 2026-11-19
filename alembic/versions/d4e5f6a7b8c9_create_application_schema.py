"""Create the initial application schema from registered SQLAlchemy models.

Revision ID: d4e5f6a7b8c9
Revises:
"""
from typing import Sequence, Union

from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from src.core.database import Base
    import src.model_registry  # noqa: F401

    later_migration_tables = {
        "data_scope_policies",
        "role_data_scope_assignments",
        "user_data_scope_assignments",
    }
    baseline_tables = [
        table for table in Base.metadata.sorted_tables
        if table.name not in later_migration_tables
    ]
    Base.metadata.create_all(
        bind=op.get_bind(), tables=baseline_tables, checkfirst=True
    )


def downgrade() -> None:
    raise NotImplementedError(
        "The initial application schema migration is intentionally forward-only."
    )
