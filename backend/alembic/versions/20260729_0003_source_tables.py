"""source 模块：source / source_run_log 表

Revision ID: 20260729_0003
Revises: 20260729_0002
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260729_0003"
down_revision: str | None = "20260729_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("plugin_key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("region", sa.String(length=32), server_default=sa.text("'GLOBAL'"), nullable=False),
        sa.Column("category", sa.String(length=32), server_default=sa.text("'NEWS'"), nullable=False),
        sa.Column("home_url", sa.String(length=500), nullable=True),
        sa.Column("config", sa.dialects.postgresql.JSONB(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("cron", sa.String(length=64), nullable=False),
        sa.Column("weight", sa.SmallInteger(), server_default=sa.text("5"), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_status", sa.String(length=32), nullable=True),
        sa.Column("consecutive_fails", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_source_plugin_key", "source", ["plugin_key"])
    op.create_index("idx_source_enabled", "source", ["enabled"])
    op.create_index("idx_source_is_deleted", "source", ["is_deleted"])
    op.create_index("idx_source_enabled_cron", "source", ["enabled", "cron"])
    op.create_index(
        "uk_source_name",
        "source",
        ["name"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )

    op.create_table(
        "source_run_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("task_id", sa.String(length=64), nullable=True),
        sa.Column("trigger_type", sa.String(length=32), server_default=sa.text("'SCHEDULED'"), nullable=False),
        sa.Column("triggered_by", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'PENDING'"), nullable=False),
        sa.Column("fetched_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("new_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["source.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_run_log_source_id", "source_run_log", ["source_id"])
    op.create_index("idx_run_log_status", "source_run_log", ["status"])
    op.create_index(
        "idx_run_log_source_time", "source_run_log", ["source_id", "started_at"]
    )


def downgrade() -> None:
    op.drop_index("idx_run_log_source_time", table_name="source_run_log")
    op.drop_index("idx_run_log_status", table_name="source_run_log")
    op.drop_index("idx_run_log_source_id", table_name="source_run_log")
    op.drop_table("source_run_log")

    op.drop_index("uk_source_name", table_name="source")
    op.drop_index("idx_source_enabled_cron", table_name="source")
    op.drop_index("idx_source_is_deleted", table_name="source")
    op.drop_index("idx_source_enabled", table_name="source")
    op.drop_index("idx_source_plugin_key", table_name="source")
    op.drop_table("source")
