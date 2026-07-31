"""pipeline 模块：article / article_embedding / event / event_article / tag / event_tag 表

Revision ID: 20260729_0004
Revises: 20260729_0003
Create Date: 2026-07-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260729_0004"
down_revision: str | None = "20260729_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 扩展（docker/postgres/init.sql 已建，这里兜底本地手动建库的场景）
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ---------------------------------------------------------------- article
    op.create_table(
        "article",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("external_id", sa.String(length=200), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=False),
        sa.Column("url_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("title_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("raw_content", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("author", sa.String(length=200), nullable=True),
        sa.Column("lang", sa.String(length=8), server_default=sa.text("'en'"), nullable=False),
        sa.Column("keywords", sa.dialects.postgresql.JSONB(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("metrics", sa.dialects.postgresql.JSONB(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("extra", sa.dialects.postgresql.JSONB(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'RAW'"), nullable=False),
        sa.Column("fail_reason", sa.String(length=500), nullable=True),
        sa.Column("event_id", sa.BigInteger(), nullable=True),
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
    op.create_index("uk_article_url_hash", "article", ["url_hash"], unique=True)
    op.create_index("idx_article_status", "article", ["status"])
    op.create_index("idx_article_title_hash", "article", ["title_hash"])
    op.create_index("idx_article_published", "article", ["published_at"])
    op.create_index("idx_article_event", "article", ["event_id"])
    # GIN trgm（高维索引，SQLAlchemy 不直接支持，用原生 SQL）
    op.execute(
        "CREATE INDEX idx_article_title_trgm ON article USING gin (title gin_trgm_ops)"
    )

    # ---------------------------------------------------------------- article_embedding
    op.create_table(
        "article_embedding",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("article_id", sa.BigInteger(), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("dim", sa.SmallInteger(), server_default=sa.text("1024"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.ForeignKeyConstraint(["article_id"], ["article.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uk_art_emb_article", "article_embedding", ["article_id"], unique=True)
    # vector 列 + HNSW 索引（必须用原生 SQL）
    op.execute("ALTER TABLE article_embedding ADD COLUMN embedding vector(1024)")
    op.execute(
        "CREATE INDEX idx_art_emb_vec ON article_embedding USING hnsw (embedding vector_cosine_ops)"
    )

    # ---------------------------------------------------------------- event
    op.create_table(
        "event",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("summary_one_line", sa.String(length=300), nullable=True),
        sa.Column("primary_article_id", sa.BigInteger(), nullable=True),
        sa.Column("region", sa.String(length=32), server_default=sa.text("'GLOBAL'"), nullable=False),
        sa.Column("categories", sa.dialects.postgresql.JSONB(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("source_count", sa.SmallInteger(), server_default=sa.text("1"), nullable=False),
        sa.Column("article_count", sa.SmallInteger(), server_default=sa.text("1"), nullable=False),
        sa.Column("heat_score", sa.Numeric(precision=6, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("value_score", sa.SmallInteger(), nullable=True),
        sa.Column("originality_score", sa.SmallInteger(), nullable=True),
        sa.Column("trend_score", sa.SmallInteger(), nullable=True),
        sa.Column("recommend_index", sa.Numeric(precision=5, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'PENDING_AI'"), nullable=False),
        sa.Column("is_pinned", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_hidden", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_manually_edited", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("manual_locked_fields", sa.dialects.postgresql.JSONB(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_event_status", "event", ["status"])
    op.create_index(
        "idx_event_recommend",
        "event",
        ["recommend_index", "last_seen_at"],
        postgresql_where=sa.text("is_deleted = false AND is_hidden = false"),
    )
    op.create_index("idx_event_heat", "event", ["heat_score"])
    op.create_index("idx_event_last_seen", "event", ["last_seen_at"])
    op.execute(
        "CREATE INDEX idx_event_title_trgm ON event USING gin (title gin_trgm_ops)"
    )
    # search_vector 生成列 + GIN 全文索引
    op.execute(
        """
        ALTER TABLE event ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('simple', coalesce(title,'')), 'A') ||
            setweight(to_tsvector('simple', coalesce(summary_one_line,'')), 'B')
        ) STORED
        """
    )
    op.execute("CREATE INDEX idx_event_search ON event USING GIN (search_vector)")

    # article.event_id 外键（article 表已建，事件表后建，回填约束）
    op.create_foreign_key(
        "fk_article_event", "article", "event", ["event_id"], ["id"], ondelete="SET NULL"
    )

    # ---------------------------------------------------------------- event_article
    op.create_table(
        "event_article",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.BigInteger(), nullable=False),
        sa.Column("article_id", sa.BigInteger(), nullable=False),
        sa.Column("match_level", sa.String(length=32), server_default=sa.text("'FINGERPRINT'"), nullable=False),
        sa.Column("similarity", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["event.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["article_id"], ["article.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uk_event_article", "event_article", ["event_id", "article_id"], unique=True)
    op.create_index("idx_ea_article", "event_article", ["article_id"])

    # ---------------------------------------------------------------- tag / event_tag
    op.create_table(
        "tag",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("type", sa.String(length=32), server_default=sa.text("'OTHER'"), nullable=False),
        sa.Column("event_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uk_tag_name", "tag", ["name"], unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.create_index("idx_tag_count", "tag", ["event_count"])

    op.create_table(
        "event_tag",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.BigInteger(), nullable=False),
        sa.Column("tag_id", sa.BigInteger(), nullable=False),
        sa.Column("weight", sa.Numeric(precision=4, scale=3), server_default=sa.text("1.0"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["event.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tag.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uk_event_tag", "event_tag", ["event_id", "tag_id"], unique=True)
    op.create_index("idx_et_tag", "event_tag", ["tag_id"])


def downgrade() -> None:
    op.drop_index("idx_et_tag", table_name="event_tag")
    op.drop_index("uk_event_tag", table_name="event_tag")
    op.drop_table("event_tag")

    op.drop_index("idx_tag_count", table_name="tag")
    op.drop_index("uk_tag_name", table_name="tag")
    op.drop_table("tag")

    op.drop_index("idx_ea_article", table_name="event_article")
    op.drop_index("uk_event_article", table_name="event_article")
    op.drop_table("event_article")

    op.execute("DROP INDEX IF EXISTS idx_event_search")
    op.execute("DROP INDEX IF EXISTS idx_event_title_trgm")
    op.drop_constraint("fk_article_event", "article", type_="foreignkey")
    op.drop_index("idx_event_last_seen", table_name="event")
    op.drop_index("idx_event_heat", table_name="event")
    op.drop_index("idx_event_recommend", table_name="event")
    op.drop_index("idx_event_status", table_name="event")
    op.drop_table("event")

    op.execute("DROP INDEX IF EXISTS idx_art_emb_vec")
    op.drop_index("uk_art_emb_article", table_name="article_embedding")
    op.drop_table("article_embedding")

    op.execute("DROP INDEX IF EXISTS idx_article_title_trgm")
    op.drop_index("idx_article_event", table_name="article")
    op.drop_index("idx_article_published", table_name="article")
    op.drop_index("idx_article_title_hash", table_name="article")
    op.drop_index("idx_article_status", table_name="article")
    op.drop_index("uk_article_url_hash", table_name="article")
    op.drop_table("article")