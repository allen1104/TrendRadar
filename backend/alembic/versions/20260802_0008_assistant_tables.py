"""add assistant tables

Revision ID: 20260802_0008
Revises: 20260731_0007
Create Date: 2026-08-02 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260802_0008"
down_revision = "20260731_0007"
branch_labels = None
depends_on = None


_JSONB = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "assistant_thread",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "event_id",
            sa.BigInteger(),
            sa.ForeignKey("event.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "title",
            sa.String(length=200),
            nullable=False,
            server_default=sa.text("'新对话'"),
        ),
        sa.Column(
            "message_count",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "total_cost_usd",
            sa.Numeric(10, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False),
            primary_key=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_index(
        "idx_thread_user_event",
        "assistant_thread",
        ["user_id", "event_id", "created_at"],
    )
    op.create_index(
        "idx_thread_user_time",
        "assistant_thread",
        ["user_id", "last_message_at"],
    )

    op.create_table(
        "assistant_message",
        sa.Column(
            "thread_id",
            sa.BigInteger(),
            sa.ForeignKey("assistant_thread.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'USER'"),
        ),
        sa.Column(
            "content",
            sa.Text(),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column("quick_question_key", sa.String(length=64), nullable=True),
        sa.Column(
            "citations",
            _JSONB,
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("model_alias", sa.String(length=100), nullable=True),
        sa.Column(
            "prompt_tokens",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "completion_tokens",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "cost_usd",
            sa.Numeric(10, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'PENDING'"),
        ),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("feedback", sa.String(length=32), nullable=True),
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False),
            primary_key=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_index(
        "idx_msg_thread",
        "assistant_message",
        ["thread_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_msg_thread", table_name="assistant_message")
    op.drop_table("assistant_message")
    op.drop_index("idx_thread_user_time", table_name="assistant_thread")
    op.drop_index("idx_thread_user_event", table_name="assistant_thread")
    op.drop_table("assistant_thread")