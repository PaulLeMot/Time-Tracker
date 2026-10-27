"""Allow deal products without a quantity.

Revision ID: 20261027_0002
Revises: 20260930_0001
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20261027_0002"
down_revision: str | None = "20260930_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "deal_products",
        "quantity",
        existing_type=sa.Integer(),
        nullable=True,
        server_default=None,
        existing_server_default=sa.text("0"),
    )


def downgrade() -> None:
    connection = op.get_bind()
    has_null_quantity = connection.execute(
        sa.text("SELECT 1 FROM deal_products WHERE quantity IS NULL LIMIT 1")
    ).scalar_one_or_none()
    if has_null_quantity is not None:
        raise RuntimeError(
            "Cannot downgrade: deal_products contains rows with quantity IS NULL. "
            "Assign explicit quantities before retrying the downgrade."
        )

    op.alter_column(
        "deal_products",
        "quantity",
        existing_type=sa.Integer(),
        nullable=False,
        server_default=sa.text("0"),
        existing_nullable=True,
    )
