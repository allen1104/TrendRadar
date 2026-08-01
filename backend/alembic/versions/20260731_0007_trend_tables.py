"""trend 模块：3 张表（event_daily_snapshot / keyword_trend / entity_trend）

Revision ID: 20260731_0007
Revises: 20260731_0006
Create Date: 2026-07-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260731_0007"
down_revision: str | None = "20260731_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -------------------------------------------------------------- event_daily_snapshot
    op.create_table(
        "event_daily_snapshot",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.BigInteger(), nullable=False),
        sa.Column("stat_date", sa.Date(), nullable=False),
        sa.Column(
            "heat_score",
            sa.Numeric(6, 2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "recommend_index",
            sa.Numeric(5, 2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "source_count",
            sa.SmallInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "article_count",
            sa.SmallInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["event_id"], ["event.id"], name="fk_snapshot_event", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uk_snapshot_event_date",
        "event_daily_snapshot",
        ["event_id", "stat_date"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.create_index(
        "idx_snapshot_date", "event_daily_snapshot", ["stat_date"]
    )
    op.create_index(
        "idx_snapshot_is_deleted", "event_daily_snapshot", ["is_deleted"]
    )

    # -------------------------------------------------------------- keyword_trend
    op.create_table(
        "keyword_trend",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("keyword", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("stat_date", sa.Date(), nullable=False),
        sa.Column(
            "event_count",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "article_count",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "heat_sum",
            sa.Numeric(10, 2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uk_kw_trend",
        "keyword_trend",
        ["keyword", "stat_date"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.create_index(
        "idx_kw_trend_date",
        "keyword_trend",
        ["stat_date", "event_count"],
    )
    op.create_index(
        "idx_kw_trend_is_deleted", "keyword_trend", ["is_deleted"]
    )

    # -------------------------------------------------------------- entity_trend
    op.create_table(
        "entity_trend",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tag_id", sa.BigInteger(), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("stat_date", sa.Date(), nullable=False),
        sa.Column(
            "event_count",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "heat_sum",
            sa.Numeric(10, 2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("avg_value_score", sa.Numeric(5, 2), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tag_id"], ["tag.id"], name="fk_entity_trend_tag", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uk_entity_trend",
        "entity_trend",
        ["tag_id", "stat_date"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.create_index(
        "idx_entity_trend_type_date",
        "entity_trend",
        ["entity_type", "stat_date", "event_count"],
    )
    op.create_index(
        "idx_entity_trend_is_deleted", "entity_trend", ["is_deleted"]
    )


def downgrade() -> None:
    op.drop_index("idx_entity_trend_is_deleted", table_name="entity_trend")
    op.drop_index("idx_entity_trend_type_date", table_name="entity_trend")
    op.drop_index("uk_entity_trend", table_name="entity_trend")
    op.drop_table("entity_trend")

    op.drop_index("idx_kw_trend_is_deleted", table_name="keyword_trend")
    op.drop_index("idx_kw_trend_date", table_name="keyword_trend")
    op.drop_index("uk_kw_trend", table_name="keyword_trend")
    op.drop_table("keyword_trend")

    op.drop_index("idx_snapshot_is_deleted", table_name="event_daily_snapshot")
    op.drop_index("idx_snapshot_date", table_name="event_daily_snapshot")
    op.drop_index("uk_snapshot_event_date", table_name="event_daily_snapshot")
    op.drop_table("event_daily_snapshot")
