"""Importing this package registers all plugins via @register_plugin decorator.

Add a new plugin by adding a file under plugins/ and importing it below.
"""

# 顺序：先具体插件，后 stub（_StubPlugin 是父类）
from . import arxiv, github_trending, hacker_news, huggingface  # noqa: F401
from . import _stubs  # noqa: F401

from .base import (  # noqa: F401
    RawItem,
    SourcePlugin,
    get_plugin_class,
    list_registered_plugins,
    normalize_url,
    register_plugin,
    run_safely,
    utcnow,
)
