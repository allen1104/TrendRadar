"""ai-engine 路由（全部仅 ADMIN 可写，统计/日志也限 ADMIN）。"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.pagination import PageParams, page_params
from app.core.schema import Page
from app.modules.admin.deps import AdminUser, DbSession
from app.modules.ai.schema import (
    CallLogItem,
    CostStatsResponse,
    EventAnalysisRequest,
    ModelCreateRequest,
    ModelResponse,
    ModelUpdateRequest,
    ProviderCreateRequest,
    ProviderListItem,
    ProviderResponse,
    ProviderTestResponse,
    PromptCreateRequest,
    PromptDryRunRequest,
    PromptDryRunResponse,
    PromptListItem,
    PromptResponse,
    PromptUpdateRequest,
    RegisteredProviderInfo,
)
from app.modules.ai.service import (
    CostService,
    ModelService,
    ProviderService,
    PromptService,
)

router = APIRouter(prefix="/admin/ai", tags=["admin:ai"])


# ============================================================ Providers


@router.get("/providers", response_model=list[ProviderListItem], summary="Provider 列表")
async def list_providers(_: AdminUser, session: DbSession) -> list[ProviderListItem]:
    return await ProviderService(session).list()


@router.get("/plugins", response_model=list[RegisteredProviderInfo], summary="已注册的 Provider 插件")
async def list_registered_plugins(_: AdminUser, session: DbSession) -> list[RegisteredProviderInfo]:
    return await ProviderService(session).list_registered()


@router.post(
    "/providers",
    response_model=ProviderResponse,
    status_code=201,
    summary="新建 Provider",
)
async def create_provider(
    payload: ProviderCreateRequest, _: AdminUser, session: DbSession
) -> ProviderResponse:
    return await ProviderService(session).create(payload)


@router.patch("/providers/{provider_id}", response_model=ProviderResponse, summary="修改 Provider")
async def update_provider(
    provider_id: int,
    payload: ProviderCreateRequest,
    _: AdminUser,
    session: DbSession,
) -> ProviderResponse:
    return await ProviderService(session).update(provider_id, payload)


@router.delete("/providers/{provider_id}", status_code=204, summary="删除 Provider")
async def delete_provider(provider_id: int, _: AdminUser, session: DbSession) -> None:
    await ProviderService(session).delete(provider_id)


@router.post(
    "/providers/{provider_id}/test",
    response_model=ProviderTestResponse,
    summary="连通性测试",
)
async def test_provider(
    provider_id: int, _: AdminUser, session: DbSession
) -> ProviderTestResponse:
    return await ProviderService(session).test_connection(provider_id)


# ============================================================ Models


@router.get("/models", response_model=list[ModelResponse], summary="模型列表")
async def list_models(_: AdminUser, session: DbSession) -> list[ModelResponse]:
    return await ModelService(session).list()


@router.post("/models", response_model=ModelResponse, status_code=201, summary="新建模型")
async def create_model(
    payload: ModelCreateRequest, _: AdminUser, session: DbSession
) -> ModelResponse:
    return await ModelService(session).create(payload)


@router.patch("/models/{model_id}", response_model=ModelResponse, summary="修改模型")
async def update_model(
    model_id: int,
    payload: ModelUpdateRequest,
    _: AdminUser,
    session: DbSession,
) -> ModelResponse:
    return await ModelService(session).update(model_id, payload)


@router.delete("/models/{model_id}", status_code=204, summary="删除模型")
async def delete_model(model_id: int, _: AdminUser, session: DbSession) -> None:
    await ModelService(session).delete(model_id)


# ============================================================ Prompts


@router.get("/prompts", response_model=list[PromptListItem], summary="Prompt 列表")
async def list_prompts(
    _: AdminUser,
    session: DbSession,
    task_key: Annotated[str | None, Query(description="按 task_key 过滤")] = None,
    only_active: Annotated[bool, Query(description="只看生效版本")] = False,
) -> list[PromptListItem]:
    return await PromptService(session).list(task_key=task_key, only_active=only_active)


@router.get("/prompts/{prompt_id}", response_model=PromptResponse, summary="Prompt 详情")
async def get_prompt(prompt_id: int, _: AdminUser, session: DbSession) -> PromptResponse:
    return await PromptService(session).get(prompt_id)


@router.post(
    "/prompts",
    response_model=PromptResponse,
    status_code=201,
    summary="新建 Prompt 版本（自动 v+1，isActive=false）",
)
async def create_prompt(
    payload: PromptCreateRequest, user: AdminUser, session: DbSession
) -> PromptResponse:
    return await PromptService(session).create(payload, created_by=user.id)


@router.patch("/prompts/{prompt_id}", response_model=PromptResponse, summary="修改 Prompt（仅未激活版本）")
async def update_prompt(
    prompt_id: int,
    payload: PromptUpdateRequest,
    _: AdminUser,
    session: DbSession,
) -> PromptResponse:
    return await PromptService(session).update(prompt_id, payload)


@router.post(
    "/prompts/{prompt_id}/activate",
    response_model=PromptResponse,
    summary="激活此版本（自动把同 task_key 其他版本置为非激活）",
)
async def activate_prompt(
    prompt_id: int, _: AdminUser, session: DbSession
) -> PromptResponse:
    return await PromptService(session).activate(prompt_id)


@router.post(
    "/prompts/{prompt_id}/dry-run",
    response_model=PromptDryRunResponse,
    summary="试运行（不写库，调用一次真实 LLM）",
)
async def dry_run_prompt(
    prompt_id: int,
    payload: PromptDryRunRequest,
    _: AdminUser,
    session: DbSession,
) -> PromptDryRunResponse:
    return await PromptService(session).dry_run(prompt_id, payload)


# ============================================================ Cost / Logs


@router.get("/cost", response_model=CostStatsResponse, summary="成本统计")
async def get_cost(
    _: AdminUser,
    session: DbSession,
    start_date: Annotated[datetime, Query(description="UTC ISO 8601")] = ...,
    end_date: Annotated[datetime, Query(description="UTC ISO 8601")] = ...,
    group_by: Annotated[str, Query(pattern="^(DAY|WEEK|MONTH)$")] = "DAY",
) -> CostStatsResponse:
    return await CostService(session).stats(start_date, end_date, group_by)


@router.get("/logs", response_model=Page[CallLogItem], summary="调用日志")
async def list_logs(
    _: AdminUser,
    session: DbSession,
    pagination: Annotated[PageParams, Depends(page_params)],
    task_key: Annotated[str | None, Query()] = None,
    model_alias: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    start_date: Annotated[datetime | None, Query()] = None,
    end_date: Annotated[datetime | None, Query()] = None,
) -> Page[CallLogItem]:
    items, total = await CostService(session).list_logs(
        page=pagination.page,
        size=pagination.size,
        task_key=task_key,
        model_alias=model_alias,
        status=status,
        start_date=start_date,
        end_date=end_date,
    )
    return Page.create(items, total, pagination.page, pagination.size)


# ============================================================ Event Analysis


@router.post(
    "/analyze",
    status_code=202,
    summary="触发事件分析（异步，pipeline 模块完成后会真正跑）",
)
async def trigger_analyze(
    payload: EventAnalysisRequest, _: AdminUser, session: DbSession
) -> dict:
    # 一期：直接同步跑（pipeline 模块尚未实现）
    from app.modules.ai.analysis import EventAnalysisService

    result = await EventAnalysisService(session).analyze_event(
        event_id=payload.event_id, force=payload.force
    )
    return {
        "eventId": payload.event_id,
        "modelAlias": result.model_alias,
        "summaryOneLine": result.summary_one_line,
        "valueScore": result.value_score,
    }
