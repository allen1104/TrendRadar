"""分页查询参数。"""

from fastapi import Query
from pydantic import BaseModel, Field


class PageParams(BaseModel):
    """全局约定：page 从 1 开始，size 默认 20 最大 100。"""

    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=100)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size

    @property
    def limit(self) -> int:
        return self.size


def page_params(
    page: int = Query(default=1, ge=1, description="页码，从 1 开始"),
    size: int = Query(default=20, ge=1, le=100, description="每页条数，最大 100"),
) -> PageParams:
    """FastAPI 依赖：解析分页参数。"""
    return PageParams(page=page, size=size)
