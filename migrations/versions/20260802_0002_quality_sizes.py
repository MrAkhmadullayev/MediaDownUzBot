"""add estimated quality sizes"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260802_0002"
down_revision: str | None = "20260802_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("download_jobs", sa.Column("available_quality_sizes", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("download_jobs", "available_quality_sizes")
