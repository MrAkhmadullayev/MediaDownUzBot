"""initial schema"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260802_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("telegram_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("first_name", sa.String(length=128), nullable=False),
        sa.Column("last_name", sa.String(length=128), nullable=True),
        sa.Column("phone_encrypted", sa.String(length=512), nullable=True),
        sa.Column("phone_last4", sa.String(length=4), nullable=True),
        sa.Column("is_registered", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("telegram_id"),
    )
    op.create_table(
        "admin_login_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_admin_login_tokens_telegram_id", "admin_login_tokens", ["telegram_id"])
    op.create_index("ix_admin_login_tokens_token_hash", "admin_login_tokens", ["token_hash"], unique=True)
    op.create_table(
        "admin_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_admin_sessions_telegram_id", "admin_sessions", ["telegram_id"])
    op.create_index("ix_admin_sessions_token_hash", "admin_sessions", ["token_hash"], unique=True)
    op.create_table(
        "download_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("source_url_encrypted", sa.Text(), nullable=True),
        sa.Column("platform", sa.Enum("youtube", "instagram", name="platform", native_enum=False), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending_analysis",
                "analyzing",
                "waiting_selection",
                "queued",
                "downloading",
                "uploading",
                "success",
                "error",
                "cancelled",
                name="jobstatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("media_type", sa.Enum("video", "audio", name="mediatype", native_enum=False), nullable=True),
        sa.Column("quality", sa.String(length=32), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("available_qualities", sa.JSON(), nullable=True),
        sa.Column("telegram_status_message_id", sa.BigInteger(), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_download_jobs_status_created", "download_jobs", ["status", "created_at"])
    op.create_index("ix_download_jobs_user_created", "download_jobs", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_download_jobs_user_created", table_name="download_jobs")
    op.drop_index("ix_download_jobs_status_created", table_name="download_jobs")
    op.drop_table("download_jobs")
    op.drop_index("ix_admin_sessions_token_hash", table_name="admin_sessions")
    op.drop_index("ix_admin_sessions_telegram_id", table_name="admin_sessions")
    op.drop_table("admin_sessions")
    op.drop_index("ix_admin_login_tokens_token_hash", table_name="admin_login_tokens")
    op.drop_index("ix_admin_login_tokens_telegram_id", table_name="admin_login_tokens")
    op.drop_table("admin_login_tokens")
    op.drop_table("users")
