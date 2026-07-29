"""通用 Pydantic 基类与分页结构。

全局约定：JSON 字段名一律 camelCase（见 SPEC.md「API」）。
"""

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

T = TypeVar("T")


class CamelModel(BaseModel):
    """所有对外 DTO 的基类。

    - 序列化用 camelCase 别名
    - 同时接受 snake_case 入参（populate_by_name）
    - 可直接从 ORM 对象构造（from_attributes）
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class Page(CamelModel, Generic[T]):  # noqa: UP046 (Pydantic compat)
    """统一分页出参：{ items, total, page, size, pages }"""

    items: list[T]
    total: int
    page: int
    size: int
    pages: int

    @classmethod
    def create(cls, items: list[T], total: int, page: int, size: int) -> "Page[T]":
        pages = (total + size - 1) // size if size > 0 else 0
        return cls(items=items, total=total, page=page, size=size, pages=pages)
