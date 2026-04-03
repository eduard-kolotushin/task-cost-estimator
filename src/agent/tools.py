"""LangChain StructuredTools — прямые вызовы WikiClient."""
from __future__ import annotations

import ast
import json
import logging
from typing import Any, Dict, List, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, field_validator

from src.config import get_wiki_space_default
from src.wiki.client import WikiClient
from src.wiki.adf import build_estimation_wiki_body
from src.wiki.prose import EstimationRow, extract_wiki_body_from_unit
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
            "чтобы проверить тело и таблицу оценок (_extracted_wiki_page_body — JSON doc редактора)."
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


_ROW_CANONICAL_KEYS = frozenset({"komanda", "komponent", "etap", "otsenka", "dekompozitsiya"})


def _normalize_row_dict(d: Dict[str, Any]) -> Dict[str, Any]:
    """Оставляем только ожидаемые поля API; регистр ключей не важен."""
    out: Dict[str, Any] = {}
    for k, v in d.items():
        if not isinstance(k, str):
            continue
        lk = k.strip().lower()
        if lk in _ROW_CANONICAL_KEYS:
            out[lk] = v
    return out


def _normalize_rows_arg(rows: Any) -> List[Dict[str, Any]]:
    """
    Модели иногда передают rows строкой (JSON или Python repr) вместо массива — приводим к списку dict.
    """
    if rows is None:
        return []
    raw: Any = rows
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return []
        try:
            raw = json.loads(s)
        except json.JSONDecodeError:
            try:
                raw = ast.literal_eval(s)
            except (ValueError, SyntaxError) as e:
                raise ValueError(
                    "rows должен быть JSON-массивом объектов или Python-списком dict; "
                    f"не удалось разобрать строку: {e}"
                ) from e
    if not isinstance(raw, list):
        raise ValueError("rows должен быть списком объектов со полями komanda, komponent, etap, otsenka, dekompozitsiya")
    out: List[Dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            out.append(_normalize_row_dict(item))
        elif hasattr(item, "model_dump"):
            out.append(_normalize_row_dict(item.model_dump()))
        else:
            raise ValueError(f"Элемент rows должен быть объектом/словарём, получено: {type(item)}")
    return out


class EstimationRowInput(BaseModel):
    komanda: str = Field(
        ...,
        description="Блок (секция таблицы): Аналитика/Проектирование | Разработка | Тестирование | Документирование",
    )
    komponent: str = Field(default="VIEW", description="Всегда VIEW")
    etap: str = Field(..., description="Имя этапа из справочника навыка оценки")
    otsenka: float = Field(
        ...,
        ge=0,
        description="Чел.-дни по строке; сумма должна сходиться с декомпозицией в dekompozitsiya",
    )
    dekompozitsiya: str = Field(
        ...,
        description=(
            "Текст декомпозиции для колонки «Декомпозиция»: подзадачи с оценками (чел.-дни), по одной логической строке на пункт; "
            "инструмент соберёт нумерованный список в wiki. Порядок строк в rows может быть любым — строки сгруппируются по komanda."
        ),
    )


class CreateWikiPageEstimationInput(BaseModel):
    summary: str = Field(..., description="Заголовок новой wiki-страницы с оценкой")
    space: str = Field(
        default="VIEW",
        description="Пространство TaskTracker (код space)",
    )
    description: str = Field(default="", description="Описание юнита (можно пусто)")
    rows: List[EstimationRowInput] = Field(
        ...,
        description=(
            "Массив объектов (не строка). Поля: komanda, komponent, etap, otsenka, dekompozitsiya. "
            "Сгенерируй dekompozitsiya как многострочный текст декомпозиции; тело wiki соберёт секции по komanda, списки из dekompozitsiya и строку Итого."
        ),
    )

    @field_validator("rows", mode="before")
    @classmethod
    def coerce_rows(cls, v: Any) -> Any:
        if isinstance(v, str):
            return _normalize_rows_arg(v)
        if isinstance(v, list):
            return [
                _normalize_row_dict(item) if isinstance(item, dict) else item for item in v
            ]
        return v


def _create_wiki_page_estimation(
    summary: str,
    space: str = "VIEW",
    description: str = "",
    rows: Optional[List[EstimationRowInput]] = None,
) -> Dict[str, Any]:
    if not rows:
        raise ValueError("rows не может быть пустым")
    parsed: List[EstimationRow] = []
    for r in rows:
        parsed.append(EstimationRow.model_validate(r.model_dump()))
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
            "Создать новую wiki-страницу с таблицей оценок. "
            "Ты задаёшь декомпозицию в поле dekompozitsiya (многострочный текст); при сохранении она превращается в нумерованный список в колонке «Декомпозиция». "
            "Таблица в wiki: заголовок → секции по komanda (как в example_wiki_page_est_table.txt) → строки данных → «Итого». "
            "rows: {komanda, komponent, etap, otsenka, dekompozitsiya}; komponent=VIEW; оценки в чел.-днях; otsenka = сумма пунктов декомпозиции по строке."
        ),
        func=_create_wiki_page_estimation,
        args_schema=CreateWikiPageEstimationInput,
    )


class UpdateWikiPageInput(BaseModel):
    code: str = Field(..., description="Код wiki-юнита для обновления")
    wiki_page_body_json: str = Field(
        ...,
        description="Полное тело wiki_page_body: строка JSON документа редактора (TipTap/ProseMirror, type: doc)",
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


class LinkWikiParentChildInput(BaseModel):
    parent: str = Field(..., description="Код родительской wiki-страницы, например VIEW-8278")
    child: str = Field(
        ...,
        description="Код дочерней wiki-страницы (поле code из ответа create_wiki_page_estimation)",
    )


def _link_wiki_parent_child(parent: str, child: str) -> Dict[str, Any]:
    client = _get_client()
    return client.link_wiki_parent_child(parent=parent, child=child)


def link_wiki_parent_child_tool() -> StructuredTool:
    return StructuredTool.from_function(
        name="link_wiki_parent_child",
        description=(
            "Связать wiki-страницы в иерархии: сделать child дочерней для parent "
            "(PATCH hierarchy/link). Вызывай после успешного create_wiki_page_estimation: "
            "parent — код родителя из запроса пользователя, child — code из ответа создания."
        ),
        func=_link_wiki_parent_child,
        args_schema=LinkWikiParentChildInput,
    )


def all_tools() -> List[StructuredTool]:
    return [
        get_task_definition_tool(),
        get_wiki_page_tool(),
        get_wiki_hierarchy_tool(),
        create_wiki_page_estimation_tool(),
        update_wiki_page_tool(),
        link_wiki_parent_child_tool(),
    ]
