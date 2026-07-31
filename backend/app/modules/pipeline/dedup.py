"""pipeline 纯函数：去重 / 哈希 / 标题归一化。

无外部依赖（除 stdlib），可离线单测。
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

# 标题归一化：去标点 / 小写 / 压缩空白 / NFKC
_PUNCT_RE = re.compile(r"[^\w\s]+", re.UNICODE)
_WS_RE = re.compile(r"\s+", re.UNICODE)


def normalize_title(title: str) -> str:
    """归一化标题用于指纹匹配。"""
    if not title:
        return ""
    # NFKC：全角→半角、兼容字符折叠
    s = unicodedata.normalize("NFKC", title)
    # 去标点
    s = _PUNCT_RE.sub(" ", s)
    # 压缩空白 + 去首尾
    s = _WS_RE.sub(" ", s).strip()
    return s.lower()


def url_hash(url: str) -> str:
    """对归一化后的 URL 计算 SHA256 哈希。"""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def title_hash(title: str) -> str:
    """对归一化后的标题计算 SHA256 哈希。"""
    return hashlib.sha256(normalize_title(title).encode("utf-8")).hexdigest()