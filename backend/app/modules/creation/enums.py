"""creation 模块枚举（按 SPEC-creation.md）。"""

from __future__ import annotations

from enum import StrEnum


class Platform(StrEnum):
    """creation_draft.platform。"""

    WECHAT = "WECHAT"      # 微信公众号
    BLOG = "BLOG"          # 技术博客
    WEIBO = "WEIBO"        # 微博
    XHS = "XHS"            # 小红书
    ZHIHU = "ZHIHU"        # 知乎
    MARKDOWN = "MARKDOWN"  # 纯 Markdown


class Style(StrEnum):
    """creation_draft.style。"""

    TECHNICAL = "TECHNICAL"    # 技术分析
    MARKETING = "MARKETING"    # 营销风格
    DEEP_DIVE = "DEEP_DIVE"    # 深度解读
    NEWS = "NEWS"              # 新闻报道
    CASUAL = "CASUAL"          # 轻松科普


class DraftStatus(StrEnum):
    """creation_draft.status。"""

    GENERATING = "GENERATING"
    DONE = "DONE"
    FAILED = "FAILED"


class ExportFormat(StrEnum):
    """导出格式。"""

    MARKDOWN = "MARKDOWN"
    HTML = "HTML"
    WECHAT_HTML = "WECHAT_HTML"
    TXT = "TXT"