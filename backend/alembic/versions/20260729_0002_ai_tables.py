"""ai-engine 模块：5 张表

Revision ID: 20260729_0002
Revises: 20260729_0001
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260729_0002"
down_revision: str | None = "20260729_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_provider",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "provider_key",
            sa.String(length=64),
            server_default=sa.text("'openai_compatible'"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=True),
        sa.Column("api_key", sa.String(length=500), nullable=True),
        sa.Column(
            "extra_config",
            sa.dialects.postgresql.JSONB(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_ai_provider_enabled", "ai_provider", ["enabled"])
    op.create_index("idx_ai_provider_is_deleted", "ai_provider", ["is_deleted"])
    op.create_index(
        "uk_ai_provider_name",
        "ai_provider",
        ["name"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )

    op.create_table(
        "ai_model",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("provider_id", sa.BigInteger(), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("alias", sa.String(length=100), nullable=False),
        sa.Column("model_type", sa.String(length=32), server_default=sa.text("'CHAT'"), nullable=False),
        sa.Column("context_window", sa.Integer(), server_default=sa.text("128000"), nullable=False),
        sa.Column("max_output_tokens", sa.Integer(), server_default=sa.text("4096"), nullable=False),
        sa.Column(
            "supports_json_schema", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("price_input_per_1m", sa.Numeric(10, 4), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "price_output_per_1m", sa.Numeric(10, 4), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("embedding_dim", sa.SmallInteger(), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.ForeignKeyConstraint(
            ["provider_id"], ["ai_provider.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_ai_model_provider", "ai_model", ["provider_id"])
    op.create_index("idx_ai_model_enabled", "ai_model", ["enabled"])
    op.create_index("idx_ai_model_is_deleted", "ai_model", ["is_deleted"])
    op.create_index("idx_ai_model_provider_type", "ai_model", ["provider_id", "model_type"])
    op.create_index(
        "uk_ai_model_alias",
        "ai_model",
        ["alias"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )

    op.create_table(
        "prompt_template",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("task_key", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("user_prompt", sa.Text(), nullable=False),
        sa.Column(
            "variables",
            sa.dialects.postgresql.JSONB(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column("model_alias", sa.String(length=100), nullable=True),
        sa.Column("temperature", sa.Float(), server_default=sa.text("0.3"), nullable=False),
        sa.Column("max_tokens", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_prompt_task_key", "prompt_template", ["task_key"])
    op.create_index("idx_prompt_is_active", "prompt_template", ["is_active"])
    op.create_index("idx_prompt_is_deleted", "prompt_template", ["is_deleted"])
    op.create_index(
        "uk_prompt_task_version",
        "prompt_template",
        ["task_key", "version"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.create_index(
        "uk_prompt_task_active",
        "prompt_template",
        ["task_key"],
        unique=True,
        postgresql_where=sa.text("is_active = true AND is_deleted = false"),
    )

    op.create_table(
        "ai_call_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column("task_key", sa.String(length=64), nullable=False),
        sa.Column("model_id", sa.BigInteger(), nullable=True),
        sa.Column("model_alias", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.Integer(), nullable=True),
        sa.Column("target_type", sa.String(length=32), nullable=True),
        sa.Column("target_id", sa.BigInteger(), nullable=True),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("cost_usd", sa.Numeric(10, 6), server_default=sa.text("0"), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'SUCCESS'"), nullable=False),
        sa.Column("retry_count", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("error_message", sa.String(length=1000), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_call_log_trace_id", "ai_call_log", ["trace_id"])
    op.create_index("idx_call_log_task_key", "ai_call_log", ["task_key"])
    op.create_index("idx_call_log_time", "ai_call_log", ["created_at"])
    op.create_index(
        "idx_call_log_model_time", "ai_call_log", ["model_alias", "created_at"]
    )
    op.create_index(
        "idx_call_log_target", "ai_call_log", ["target_type", "target_id"]
    )
    op.create_index("idx_call_log_is_deleted", "ai_call_log", ["is_deleted"])

    op.create_table(
        "event_analysis",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.BigInteger(), nullable=False),
        sa.Column("summary_one_line", sa.String(length=300), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("key_points", sa.dialects.postgresql.JSONB(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("innovations", sa.dialects.postgresql.JSONB(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("audience", sa.dialects.postgresql.JSONB(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("categories", sa.dialects.postgresql.JSONB(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("tags", sa.dialects.postgresql.JSONB(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("value_score", sa.SmallInteger(), nullable=False),
        sa.Column("originality_score", sa.SmallInteger(), nullable=False),
        sa.Column("trend_score", sa.SmallInteger(), nullable=False),
        sa.Column("worth_article", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("worth_article_why", sa.String(length=500), nullable=True),
        sa.Column("worth_research", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("worth_research_why", sa.String(length=500), nullable=True),
        sa.Column("model_alias", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.Integer(), nullable=False),
        sa.Column(
            "analyzed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_event_analysis_event_id", "event_analysis", ["event_id"])
    op.create_index("idx_event_analysis_is_deleted", "event_analysis", ["is_deleted"])
    op.create_index(
        "uk_event_analysis_event",
        "event_analysis",
        ["event_id"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )


def downgrade() -> None:
    op.drop_index("uk_event_analysis_event", table_name="event_analysis")
    op.drop_index("idx_event_analysis_is_deleted", table_name="event_analysis")
    op.drop_index("idx_event_analysis_event_id", table_name="event_analysis")
    op.drop_table("event_analysis")

    op.drop_index("idx_call_log_is_deleted", table_name="ai_call_log")
    op.drop_index("idx_call_log_target", table_name="ai_call_log")
    op.drop_index("idx_call_log_model_time", table_name="ai_call_log")
    op.drop_index("idx_call_log_time", table_name="ai_call_log")
    op.drop_index("idx_call_log_task_key", table_name="ai_call_log")
    op.drop_index("idx_call_log_trace_id", table_name="ai_call_log")
    op.drop_table("ai_call_log")

    op.drop_index("uk_prompt_task_active", table_name="prompt_template")
    op.drop_index("uk_prompt_task_version", table_name="prompt_template")
    op.drop_index("idx_prompt_is_deleted", table_name="prompt_template")
    op.drop_index("idx_prompt_is_active", table_name="prompt_template")
    op.drop_index("idx_prompt_task_key", table_name="prompt_template")
    op.drop_table("prompt_template")

    op.drop_index("uk_ai_model_alias", table_name="ai_model")
    op.drop_index("idx_ai_model_provider_type", table_name="ai_model")
    op.drop_index("idx_ai_model_is_deleted", table_name="ai_model")
    op.drop_index("idx_ai_model_enabled", table_name="ai_model")
    op.drop_index("idx_ai_model_provider", table_name="ai_model")
    op.drop_table("ai_model")

    op.drop_index("uk_ai_provider_name", table_name="ai_provider")
    op.drop_index("idx_ai_provider_is_deleted", table_name="ai_provider")
    op.drop_index("idx_ai_provider_enabled", table_name="ai_provider")
    op.drop_table("ai_provider")
