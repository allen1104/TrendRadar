"""auth 模块：user / user_preference 表

Revision ID: 20260729_0001
Revises:
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260729_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 扩展（docker/postgres/init.sql 已建，这里兜底本地手动建库的场景）
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "user",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=120), nullable=False),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("password_hash", sa.String(length=128), nullable=False),
        sa.Column("avatar_url", sa.String(length=500), nullable=True),
        sa.Column("role", sa.String(length=32), server_default=sa.text("'USER'"), nullable=False),
        sa.Column(
            "status", sa.String(length=32), server_default=sa.text("'ACTIVE'"), nullable=False
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_user_is_deleted", "user", ["is_deleted"])
    op.create_index("idx_user_role_status", "user", ["role", "status"])
    op.create_index(
        "uk_user_email", "user", ["email"], unique=True, postgresql_where=sa.text("is_deleted = false")
    )
    op.create_index(
        "uk_user_username",
        "user",
        ["username"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )

    op.create_table(
        "user_preference",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "default_scope",
            sa.String(length=32),
            server_default=sa.text("'TODAY'"),
            nullable=False,
        ),
        sa.Column(
            "followed_categories",
            sa.dialects.postgresql.JSONB(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column(
            "followed_tags",
            sa.dialects.postgresql.JSONB(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column(
            "muted_sources",
            sa.dialects.postgresql.JSONB(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column(
            "daily_report_opt_in", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_user_preference_is_deleted", "user_preference", ["is_deleted"])
    op.create_index(
        "uk_user_pref_user",
        "user_preference",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )


def downgrade() -> None:
    op.drop_index("uk_user_pref_user", table_name="user_preference")
    op.drop_index("idx_user_preference_is_deleted", table_name="user_preference")
    op.drop_table("user_preference")

    op.drop_index("uk_user_username", table_name="user")
    op.drop_index("uk_user_email", table_name="user")
    op.drop_index("idx_user_role_status", table_name="user")
    op.drop_index("idx_user_is_deleted", table_name="user")
    op.drop_table("user")
