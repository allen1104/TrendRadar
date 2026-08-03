"""add report tables

Revision ID: 20260802_0010
Revises: 20260802_0009
Create Date: 2026-08-02 00:00:00

按 doc/SPEC-report.md：
  - report（日报）
  - report_item（日报条目）
  - report_subscription（订阅）
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260802_0010"
down_revision = "20260802_0009"
branch_labels = None
depends_on = None


_JSONB = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    # ------------------------------------------------------------ report
    op.create_table(
        "report",
        sa.Column("report_type", sa.String(length=32), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column(
            "title",
            sa.String(length=300),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column("intro", sa.Text(), nullable=True),
        sa.Column("outro", sa.Text(), nullable=True),
        sa.Column(
            "content_md",
            sa.Text(),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column("content_edited", sa.Text(), nullable=True),
        sa.Column(
            "item_count",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'GENERATING'"),
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "view_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("model_alias", sa.String(length=100), nullable=True),
        sa.Column(
            "cost_usd",
            sa.Numeric(10, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("error_message", sa.String(length=500), nullable=True),
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
        sa.UniqueConstraint(
            "report_type",
            "report_date",
            name="uk_report_type_date",
        ),
    )
    op.create_index(
        "idx_report_status_date",
        "report",
        ["status", "report_date"],
    )

    # ------------------------------------------------------------ report_item
    op.create_table(
        "report_item",
        sa.Column(
            "report_id",
            sa.BigInteger(),
            sa.ForeignKey("report.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "event_id",
            sa.BigInteger(),
            sa.ForeignKey("event.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "section",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column(
            "sort_order",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "headline",
            sa.String(length=300),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column(
            "brief",
            sa.Text(),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "is_top",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
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
        "idx_report_item",
        "report_item",
        ["report_id", "section", "sort_order"],
    )
    op.create_index(
        "idx_report_item_event",
        "report_item",
        ["event_id"],
    )

    # ------------------------------------------------------------ report_subscription
    op.create_table(
        "report_subscription",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "report_types",
            _JSONB,
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "channel",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'SITE'"),
        ),
        sa.Column("webhook_url", sa.String(length=500), nullable=True),
        sa.Column("rss_token", sa.String(length=64), nullable=True),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
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
        "uk_subscription_user",
        "report_subscription",
        ["user_id"],
        unique=True,
    )
    op.create_index(
        "uk_subscription_rss_token",
        "report_subscription",
        ["rss_token"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uk_subscription_rss_token", table_name="report_subscription")
    op.drop_index("uk_subscription_user", table_name="report_subscription")
    op.drop_table("report_subscription")
    op.drop_index("idx_report_item_event", table_name="report_item")
    op.drop_index("idx_report_item", table_name="report_item")
    op.drop_table("report_item")
    op.drop_index("idx_report_status_date", table_name="report")
    op.drop_table("report")
