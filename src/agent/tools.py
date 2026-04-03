"""LangChain StructuredTools — прямые вызовы WikiClient."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from src.config import get_wiki_space_default
from src.wiki.client import WikiClient
from src.wiki.prose import EstimationRow, build_estimation_wiki_body, extract_wiki_body_from_unit
from src.wiki.task_unit import format_task_unit_for_prompt

log = logging.getLogger(__name__)

_client: Optional[WikiClient] = None


def _get_client() -> WikiClient:
    global _client
    if _client is None:
        _client = WikiClient.from_env()
    return _client


class GetTaskDefinitionInput(BaseModel):
    code: str = Field(..., description="Код юнита задачи TaskTracker, например VIEW-8168")


def _get_task_definition(code: str) -> Dict[str, Any]:
    """GET /rest/api/unit/v2/{code}?validatorEnabled=true — задача не из wiki-плагина."""
    client = _get_client()
    unit = client.get_task_unit(code)
    out: Dict[str, Any] = dict(unit) if isinstance(unit, dict) else {"raw": unit}
    if isinstance(unit, dict):
        out["_formatted_task_context"] = format_task_unit_for_prompt(unit)
    return out


def get_task_definition_tool() -> StructuredTool:
    return StructuredTool.from_function(
        name="get_task_definition",
        description=(
            "Загрузить определение задачи по коду юнита (GET /rest/api/unit/v2/{code}). "
            "Используй для оценки: поле _formatted_task_context — краткий текст для анализа; "
            "также в ответе полный JSON юнита (summary, description, attributes)."
        ),
        func=_get_task_definition,
        args_schema=GetTaskDefinitionInput,
    )


class GetWikiPageInput(BaseModel):
    code: str = Field(
        ...,
        description="Код wiki-страницы (юнит wiki), например код после create_wiki_page_estimation",
    )


def _get_wiki_page(code: str) -> Dict[str, Any]:
    """GET wiki-плагин — для проверки созданной страницы с оценками, не для исходной задачи."""
    client = _get_client()
    unit = client.get_wiki_unit(code)
    body = extract_wiki_body_from_unit(unit)
    out: Dict[str, Any] = dict(unit) if isinstance(unit, dict) else {"raw": unit}
    out["_extracted_wiki_page_body"] = body
    return out


def get_wiki_page_tool() -> StructuredTool:
    return StructuredTool.from_function(
        name="get_wiki_page",
        description=(
            "Загрузить **wiki-страницу** через wiki-плагин (не тот же ответ, что у задачи). "
            "Используй после create_wiki_page_estimation: передай **код созданной страницы**, "
            "чтобы проверить тело и таблицу оценок (_extracted_wiki_page_body — JSON ProseMirror)."
        ),
        func=_get_wiki_page,
        args_schema=GetWikiPageInput,
    )


class GetWikiHierarchyInput(BaseModel):
    spaces: Optional[List[str]] = Field(
        default=None,
        description=(
            "Коды пространств (например VIEW). Если не указано — одно пространство из WIKI_SPACE."
        ),
    )


def _get_wiki_hierarchy(spaces: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Иерархия wiki: param.root всегда null на стороне клиента (все страницы в space).
    """
    client = _get_client()
    sp = spaces if spaces else [get_wiki_space_default()]
    return client.get_wiki_hierarchy(spaces=sp)


def get_wiki_hierarchy_tool() -> StructuredTool:
    return StructuredTool.from_function(
        name="get_wiki_hierarchy",
        description=(
            "Получить иерархию wiki-страниц в пространстве(ах). "
            "Внутри всегда запрашивается полное дерево (root=null). "
            "Используй для обзора структуры страниц перед/после создания оценки."
        ),
        func=_get_wiki_hierarchy,
        args_schema=GetWikiHierarchyInput,
    )


class EstimationRowInput(BaseModel):
    komanda: str
    komponent: str = "VIEW"
    etap: str
    otsenka: float = Field(..., ge=0, description="Итог по строке, чел.-дни")
    kommentariy: str


class CreateWikiPageEstimationInput(BaseModel):
    summary: str = Field(..., description="Заголовок новой wiki-страницы с оценкой")
    space: str = Field(
        default="VIEW",
        description="Пространство TaskTracker (код space)",
    )
    description: str = Field(default="", description="Описание юнита (можно пусто)")
    rows: List[EstimationRowInput] = Field(
        ...,
        description="Строки таблицы оценок: Команда, Компонент (VIEW), Этап, Оценка (чел.-дни), Комментарий",
    )


def _create_wiki_page_estimation(
    summary: str,
    space: str = "VIEW",
    description: str = "",
    rows: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    if not rows:
        raise ValueError("rows не может быть пустым")
    parsed: List[EstimationRow] = []
    for r in rows:
        if isinstance(r, dict):
            parsed.append(EstimationRow.model_validate(r))
        else:
            parsed.append(EstimationRow.model_validate(r.model_dump() if hasattr(r, "model_dump") else r))
    wiki_body = build_estimation_wiki_body(parsed)
    client = _get_client()
    result = client.create_wiki_page(
        summary=summary,
        space=space,
        description=description,
        wiki_page_body=wiki_body,
    )
    log.info("create_wiki_page_estimation: summary=%s space=%s", summary, space)
    return result if isinstance(result, dict) else {"result": result}


def create_wiki_page_estimation_tool() -> StructuredTool:
    return StructuredTool.from_function(
        name="create_wiki_page_estimation",
        description=(
            "Создать новую wiki-страницу с таблицей оценок (5 колонок). "
            "Компонент в каждой строке — VIEW; оценки только в чел.-дни; "
            "в Комментарий — декомпозиция подзадач с оценками и обоснование; "
            "Оценка = сумма подзадач по строке."
        ),
        func=_create_wiki_page_estimation,
        args_schema=CreateWikiPageEstimationInput,
    )


class UpdateWikiPageInput(BaseModel):
    code: str = Field(..., description="Код wiki-юнита для обновления")
    wiki_page_body_json: str = Field(
        ...,
        description="Полное тело wiki_page_body: строка JSON документа ProseMirror",
    )


def _update_wiki_page(code: str, wiki_page_body_json: str) -> Dict[str, Any]:
    # Проверка JSON
    try:
        json.loads(wiki_page_body_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"wiki_page_body_json не является валидным JSON: {e}") from e
    client = _get_client()
    result = client.update_wiki_unit(code, wiki_page_body=wiki_page_body_json)
    return result if isinstance(result, dict) else {"result": result}


def update_wiki_page_tool() -> StructuredTool:
    return StructuredTool.from_function(
        name="update_wiki_page",
        description=(
            "Обновить тело существующей wiki-страницы (PATCH). "
            "Передайте wiki_page_body как одну строку JSON (как в API)."
        ),
        func=_update_wiki_page,
        args_schema=UpdateWikiPageInput,
    )


def all_tools() -> List[StructuredTool]:
    return [
        get_task_definition_tool(),
        get_wiki_page_tool(),
        get_wiki_hierarchy_tool(),
        create_wiki_page_estimation_tool(),
        update_wiki_page_tool(),
    ]
