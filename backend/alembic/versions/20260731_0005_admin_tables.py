"""admin 模块：3 张表（system_config / task_run_log / audit_log）

Revision ID: 20260731_0005
Revises: 20260729_0004
Create Date: 2026-07-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260731_0005"
down_revision: str | None = "20260729_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---------------------------------------------------------- system_config
    op.create_table(
        "system_config",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("config_key", sa.String(length=100), nullable=False),
        sa.Column("config_value", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column(
            "value_type",
            sa.String(length=32),
            server_default=sa.text("'STRING'"),
            nullable=False,
        ),
        sa.Column("group_name", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("min_value", sa.Numeric(), nullable=True),
        sa.Column("max_value", sa.Numeric(), nullable=True),
        sa.Column(
            "is_editable", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "requires_rerun",
            sa.Boolean(),
            server_default=sa.text("false"),
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
    op.create_index("uk_config_key", "system_config", ["config_key"], unique=True)
    op.create_index("idx_config_group", "system_config", ["group_name"])
    op.create_index("idx_config_is_deleted", "system_config", ["is_deleted"])

    # ---------------------------------------------------------- task_run_log
    op.create_table(
        "task_run_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("task_name", sa.String(length=120), nullable=False),
        sa.Column("task_id", sa.String(length=64), nullable=True),
        sa.Column(
            "trigger_type",
            sa.String(length=32),
            server_default=sa.text("'SCHEDULED'"),
            nullable=False,
        ),
        sa.Column("triggered_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "args_summary",
            sa.dialects.postgresql.JSONB(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'PENDING'"),
            nullable=False,
        ),
        sa.Column("result_summary", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "retry_count", sa.SmallInteger(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("traceback", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
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
    op.create_index("uk_task_run_task_id", "task_run_log", ["task_id"], unique=True)
    op.create_index(
        "idx_task_run_name_time", "task_run_log", ["task_name", "started_at"]
    )
    op.create_index("idx_task_run_status", "task_run_log", ["status"])
    op.create_index("idx_task_run_is_deleted", "task_run_log", ["is_deleted"])

    # ---------------------------------------------------------- audit_log
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("username", sa.String(length=50), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.BigInteger(), nullable=True),
        sa.Column("before_value", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("after_value", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
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
    op.create_index("idx_audit_time", "audit_log", ["created_at"])
    op.create_index("idx_audit_user", "audit_log", ["user_id", "created_at"])
    op.create_index(
        "idx_audit_target", "audit_log", ["target_type", "target_id"]
    )
    op.create_index("idx_audit_action", "audit_log", ["action"])
    op.create_index("idx_audit_trace_id", "audit_log", ["trace_id"])


def downgrade() -> None:
    op.drop_index("idx_audit_trace_id", table_name="audit_log")
    op.drop_index("idx_audit_action", table_name="audit_log")
    op.drop_index("idx_audit_target", table_name="audit_log")
    op.drop_index("idx_audit_user", table_name="audit_log")
    op.drop_index("idx_audit_time", table_name="audit_log")
    op.drop_table("audit_log")

    op.drop_index("idx_task_run_is_deleted", table_name="task_run_log")
    op.drop_index("idx_task_run_status", table_name="task_run_log")
    op.drop_index("idx_task_run_name_time", table_name="task_run_log")
    op.drop_index("uk_task_run_task_id", table_name="task_run_log")
    op.drop_table("task_run_log")

    op.drop_index("idx_config_is_deleted", table_name="system_config")
    op.drop_index("idx_config_group", table_name="system_config")
    op.drop_index("uk_config_key", table_name="system_config")
    op.drop_table("system_config")