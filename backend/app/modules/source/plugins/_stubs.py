"""未实现的采集器占位插件。

共 4 个：product_hunt (需 token) + jiqizhixin + qbitai + infoq_cn。
注册到全局以保证后台列「可选插件」完整，但 fetch/parse/normalize 抛 NotImplementedError，
避免在一期被错误地启用。后续按需补实现。
"""

from __future__ import annotations

from app.modules.source.plugins.base import SourcePlugin, register_plugin


class _StubPlugin(SourcePlugin):
    """所有 stub 的基类。子类只需声明 plugin_key / display_name / cron。"""

    async def fetch(self):  # type: ignore[override]
        raise NotImplementedError(
            f"{self.plugin_key} 暂未实现（target 实现优先级见 PROGRESS.md）"
        )

    def parse(self, raw):  # type: ignore[override]
        raise NotImplementedError

    def normalize(self, parsed):  # type: ignore[override]
        raise NotImplementedError


@register_plugin
class ProductHuntPlugin(_StubPlugin):
    plugin_key = "product_hunt"
    display_name = "Product Hunt"
    region = "GLOBAL"
    category = "PRODUCT"
    default_cron = "45 * * * *"
    default_weight = 6


@register_plugin
class JiqizhixinPlugin(_StubPlugin):
    plugin_key = "jiqizhixin"
    display_name = "机器之心"
    region = "CN"
    category = "NEWS"
    default_cron = "10 * * * *"
    default_weight = 8


@register_plugin
class QbitaiPlugin(_StubPlugin):
    plugin_key = "qbitai"
    display_name = "量子位"
    region = "CN"
    category = "NEWS"
    default_cron = "20 * * * *"
    default_weight = 7


@register_plugin
class InfoqCnPlugin(_StubPlugin):
    plugin_key = "infoq_cn"
    display_name = "InfoQ 中国"
    region = "CN"
    category = "BLOG"
    default_cron = "40 * * * *"
    default_weight = 7
