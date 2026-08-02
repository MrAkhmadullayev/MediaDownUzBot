"""add media metadata and telegram file caches"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260802_0003"
down_revision: str | None = "20260802_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "media_source_cache",
        sa.Column("source_key", sa.String(length=64), nullable=False),
        sa.Column(
            "platform",
            sa.Enum("youtube", "instagram", name="platform", native_enum=False),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("available_qualities", sa.JSON(), nullable=False),
        sa.Column("available_quality_sizes", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("source_key"),
    )
    op.create_table(
        "telegram_file_cache",
        sa.Column("source_key", sa.String(length=64), nullable=False),
        sa.Column(
            "media_type",
            sa.Enum("video", "audio", name="mediatype", native_enum=False),
            nullable=False,
        ),
        sa.Column("quality", sa.String(length=32), nullable=False),
        sa.Column("telegram_file_id", sa.String(length=512), nullable=False),
        sa.Column("telegram_file_unique_id", sa.String(length=256), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("source_key", "media_type", "quality"),
    )
    op.create_index(
        "ix_telegram_file_cache_last_used",
        "telegram_file_cache",
        ["last_used_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_telegram_file_cache_last_used", table_name="telegram_file_cache")
    op.drop_table("telegram_file_cache")
    op.drop_table("media_source_cache")
