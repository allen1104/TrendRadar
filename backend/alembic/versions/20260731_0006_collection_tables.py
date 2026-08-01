"""collection 模块：2 张表（collection_folder / collection_item）

Revision ID: 20260731_0006
Revises: 20260731_0005
Create Date: 2026-07-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260731_0006"
down_revision: str | None = "20260731_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -------------------------------------------------------------- collection_folder
    op.create_table(
        "collection_folder",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("color", sa.String(length=16), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("item_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
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
        "uk_folder_user_name",
        "collection_folder",
        ["user_id", "name"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.create_index("idx_folder_user", "collection_folder", ["user_id", "sort_order"])
    op.create_index(
        "idx_folder_is_deleted", "collection_folder", ["is_deleted"]
    )

    # -------------------------------------------------------------- collection_item
    op.create_table(
        "collection_item",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("folder_id", sa.BigInteger(), nullable=False),
        sa.Column("event_id", sa.BigInteger(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "user_tags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column(
            "read_status",
            sa.String(length=32),
            server_default=sa.text("'UNREAD'"),
            nullable=False,
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
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
            ["event_id"], ["event.id"], name="fk_item_event", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["folder_id"], ["collection_folder.id"], name="fk_item_folder", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uk_item_user_event",
        "collection_item",
        ["user_id", "event_id"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.create_index(
        "idx_item_folder", "collection_item", ["folder_id", "created_at"]
    )
    op.create_index(
        "idx_item_read_status", "collection_item", ["user_id", "read_status"]
    )
    op.create_index("idx_item_is_deleted", "collection_item", ["is_deleted"])
    # GIN 索引：加速 user_tags 过滤
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_item_tags ON collection_item USING GIN (user_tags)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_item_tags")
    op.drop_index("idx_item_is_deleted", table_name="collection_item")
    op.drop_index("idx_item_read_status", table_name="collection_item")
    op.drop_index("idx_item_folder", table_name="collection_item")
    op.drop_index("uk_item_user_event", table_name="collection_item")
    op.drop_table("collection_item")

    op.drop_index("idx_folder_is_deleted", table_name="collection_folder")
    op.drop_index("idx_folder_user", table_name="collection_folder")
    op.drop_index("uk_folder_user_name", table_name="collection_folder")
    op.drop_table("collection_folder")