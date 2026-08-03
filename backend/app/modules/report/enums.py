"""report 模块枚举（按 SPEC-report.md）。"""

from __future__ import annotations

from enum import StrEnum


class ReportType(StrEnum):
    """report.report_type。"""

    AI = "AI"          # AI 日报
    TECH = "TECH"      # 科技日报
    GITHUB = "GITHUB"  # GitHub 日报
    AGENT = "AGENT"    # Agent 日报


class ReportStatus(StrEnum):
    """report.status。"""

    GENERATING = "GENERATING"
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


class ExportFormat(StrEnum):
    """日报导出格式。"""

    MARKDOWN = "MARKDOWN"
    HTML = "HTML"
    PDF = "PDF"
    WECHAT_HTML = "WECHAT_HTML"


class SubscriptionChannel(StrEnum):
    """订阅推送渠道。"""

    SITE = "SITE"
    EMAIL = "EMAIL"
    WEBHOOK = "WEBHOOK"


# 各类型最小条目数（候选池不足时跳过当日）
REPORT_MIN_ITEMS: dict[str, int] = {
    ReportType.AI.value: 5,
    ReportType.TECH.value: 6,
    ReportType.GITHUB.value: 4,
    ReportType.AGENT.value: 3,
}

# 各类型最大条目数
REPORT_MAX_ITEMS: dict[str, int] = {
    ReportType.AI.value: 12,
    ReportType.TECH.value: 15,
    ReportType.GITHUB.value: 12,
    ReportType.AGENT.value: 10,
}

# 各类型选题筛选 SQL 片段（按 report_date 当日的 ANALYZED 事件）
REPORT_FILTER_SQL: dict[str, str] = {
    # AI：categories 包含 AI / LLM / AGENT / MCP
    ReportType.AI.value: (
        "AND (categories ? 'AI' OR categories ? 'LLM' "
        "OR categories ? 'AGENT' OR categories ? 'MCP')"
    ),
    # TECH：所有 ANALYZED 事件（不额外过滤 category）
    ReportType.TECH.value: "",
    # GITHUB：关联 article 的 source.category = 'CODE'
    ReportType.GITHUB.value: (
        "AND EXISTS (SELECT 1 FROM event_article ea "
        "JOIN article a ON ea.article_id=a.id "
        "JOIN source s ON a.source_id=s.id "
        "WHERE ea.event_id=event.id AND ea.is_deleted=false "
        "AND a.is_deleted=false AND s.category='CODE' "
        "AND s.is_deleted=false)"
    ),
    # AGENT：categories 包含 AGENT / MCP
    ReportType.AGENT.value: "AND (categories ? 'AGENT' OR categories ? 'MCP')",
}

# 板块划分（写到 Prompt + 前端渲染用）
REPORT_SECTIONS: dict[str, list[str]] = {
    ReportType.AI.value: ["头条", "模型发布", "应用与产品", "研究进展"],
    ReportType.TECH.value: ["头条", "行业动态", "产品发布", "商业与创投"],
    ReportType.GITHUB.value: ["今日最热", "新星项目", "重要更新"],
    ReportType.AGENT.value: ["头条", "框架与工具", "实践案例", "协议与标准"],
}

# 板块中文名映射（用于响应）
REPORT_TYPE_NAMES: dict[str, str] = {
    ReportType.AI.value: "AI 日报",
    ReportType.TECH.value: "科技日报",
    ReportType.GITHUB.value: "GitHub 日报",
    ReportType.AGENT.value: "Agent 日报",
}
