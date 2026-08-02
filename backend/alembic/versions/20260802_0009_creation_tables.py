"""add creation_draft table

Revision ID: 20260802_0009
Revises: 20260802_0008
Create Date: 2026-08-02 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260802_0009"
down_revision = "20260802_0008"
branch_labels = None
depends_on = None


_JSONB = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "creation_draft",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "event_id",
            sa.BigInteger(),
            sa.ForeignKey("event.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("style", sa.String(length=32), nullable=False),
        sa.Column(
            "title",
            sa.String(length=300),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column(
            "content",
            sa.Text(),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column("content_edited", sa.Text(), nullable=True),
        sa.Column(
            "outline",
            _JSONB,
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("cover_suggestion", sa.String(length=500), nullable=True),
        sa.Column(
            "tags_suggestion",
            _JSONB,
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "word_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "extra_params",
            _JSONB,
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("model_alias", sa.String(length=100), nullable=True),
        sa.Column("prompt_version", sa.Integer(), nullable=True),
        sa.Column(
            "cost_usd",
            sa.Numeric(10, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'GENERATING'"),
        ),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column(
            "regenerate_count",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
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
        "idx_draft_user_time",
        "creation_draft",
        ["user_id", "created_at"],
    )
    op.create_index("idx_draft_event", "creation_draft", ["event_id"])
    op.create_index(
        "idx_draft_user_platform",
        "creation_draft",
        ["user_id", "platform"],
    )


def downgrade() -> None:
    op.drop_index("idx_draft_user_platform", table_name="creation_draft")
    op.drop_index("idx_draft_event", table_name="creation_draft")
    op.drop_index("idx_draft_user_time", table_name="creation_draft")
    op.drop_table("creation_draft")