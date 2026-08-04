"""add support conversations and broadcasts"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260804_0004"
down_revision: str | None = "20260802_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "support_tickets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("open", "closed", name="supportticketstatus", native_enum=False),
            server_default="open",
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_support_tickets_user_created", "support_tickets", ["user_id", "created_at"])
    op.create_index(
        "ix_support_tickets_status_updated", "support_tickets", ["status", "updated_at"]
    )
    op.create_table(
        "support_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column(
            "sender",
            sa.Enum("user", "admin", name="supportsender", native_enum=False),
            nullable=False,
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "delivery_status",
            sa.Enum(
                "pending", "sending", "sent", "failed", name="deliverystatus", native_enum=False
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("error_detail", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["ticket_id"], ["support_tickets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_support_messages_ticket_created", "support_messages", ["ticket_id", "created_at"]
    )
    op.create_index(
        "ix_support_messages_delivery", "support_messages", ["delivery_status", "created_at"]
    )
    op.create_table(
        "broadcasts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "processing",
                "completed",
                "partial",
                "failed",
                name="broadcaststatus",
                native_enum=False,
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("total_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("sent_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("failed_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_broadcasts_created", "broadcasts", ["created_at"])
    op.create_table(
        "broadcast_deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("broadcast_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending", "sending", "sent", "failed", name="deliverystatus", native_enum=False
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("error_detail", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["broadcast_id"], ["broadcasts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("broadcast_id", "user_id", name="uq_broadcast_delivery_user"),
    )
    op.create_index(
        "ix_broadcast_deliveries_status", "broadcast_deliveries", ["broadcast_id", "status"]
    )
    op.create_index(
        "ix_broadcast_deliveries_user", "broadcast_deliveries", ["user_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_broadcast_deliveries_user", table_name="broadcast_deliveries")
    op.drop_index("ix_broadcast_deliveries_status", table_name="broadcast_deliveries")
    op.drop_table("broadcast_deliveries")
    op.drop_index("ix_broadcasts_created", table_name="broadcasts")
    op.drop_table("broadcasts")
    op.drop_index("ix_support_messages_delivery", table_name="support_messages")
    op.drop_index("ix_support_messages_ticket_created", table_name="support_messages")
    op.drop_table("support_messages")
    op.drop_index("ix_support_tickets_status_updated", table_name="support_tickets")
    op.drop_index("ix_support_tickets_user_created", table_name="support_tickets")
    op.drop_table("support_tickets")
