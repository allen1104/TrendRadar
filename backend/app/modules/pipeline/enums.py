"""pipeline 枚举。"""

from __future__ import annotations

from enum import StrEnum


class ArticleStatus(StrEnum):
    """article 处理状态。"""

    RAW = "RAW"               # 采集刚入库
    CLEANED = "CLEANED"       # 已清洗（正文/摘要/关键词就位）
    EMBEDDED = "EMBEDDED"     # 已生成向量
    CLUSTERED = "CLUSTERED"   # 已挂到 event
    FAILED = "FAILED"         # 处理失败（具体原因看 fail_reason）
    DISCARDED = "DISCARDED"   # 丢弃（垃圾内容 / 超龄 / 语言不支持）


class EventStatus(StrEnum):
    """event 生命周期。"""

    PENDING_AI = "PENDING_AI"   # 待 AI 分析
    ANALYZING = "ANALYZING"     # 分析中
    ANALYZED = "ANALYZED"       # 已完成分析
    ARCHIVED = "ARCHIVED"       # 已归档（超过 72h 无新来源）
    AI_FAILED = "AI_FAILED"     # AI 分析失败（重试 N 次后放弃）


class MatchLevel(StrEnum):
    """article 挂到 event 时匹配的层级。"""

    FINGERPRINT = "FINGERPRINT"  # L1 url_hash / title_hash 精确命中
    TITLE = "TITLE"              # L2 pg_trgm 标题相似
    VECTOR = "VECTOR"            # L3 pgvector 余弦相似
    MANUAL = "MANUAL"            # EDITOR 人工干预（拆分/合并）


class EventRegion(StrEnum):
    """event 覆盖区域。"""

    GLOBAL = "GLOBAL"
    CN = "CN"
    MIXED = "MIXED"