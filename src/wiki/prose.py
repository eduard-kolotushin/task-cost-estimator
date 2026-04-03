"""Модель строки оценки и извлечение текста из wiki_page_body (TipTap/ProseMirror doc, узлы text)."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from pydantic import BaseModel, Field, field_validator


class EstimationRow(BaseModel):
    """Одна строка в `rows` инструмента create_wiki_page_estimation; в wiki попадает в ячейку сетки по komanda+etap."""

    komanda: str = Field(
        ...,
        description="Канонический блок: Аналитика/Проектирование | Разработка | Тестирование | Документирование — для сопоставления с секцией и строкой этапа",
    )
    komponent: str = Field(
        default="VIEW",
        description="Всегда VIEW (поле API; в wiki не отображается)",
    )
    etap: str = Field(
        ...,
        description="Точное имя этапа из справочника навыка; в таблице всегда есть полная сетка этапов — в rows указывай только заполненные",
    )
    otsenka: float = Field(
        ...,
        ge=0,
        description="Чел.-дни по строке; при ненулевой оценке сумма подзадач в dekompozitsiya должна с ней согласовываться",
    )
    dekompozitsiya: str = Field(
        default="",
        description=(
            "Многострочный текст (\\n): пункты списка в колонке «Декомпозиция». "
            "При ненулевой оценке: на каждой строке с подзадачей укажи оценку этой подзадачи в чел.-днях; сумма по строкам = otsenka. "
            "Пусто допустимо только при нулевой оценке по этапу."
        ),
    )

    @field_validator("komponent")
    @classmethod
    def component_view(cls, v: str) -> str:
        if v.strip().upper() != "VIEW":
            return "VIEW"
        return "VIEW"


def extract_text_from_wiki_body(wiki_page_body: str) -> str:
    """Рекурсивно извлекает текст из JSON тела wiki (TipTap/ProseMirror doc) для передачи в LLM."""
    try:
        data = json.loads(wiki_page_body)
    except (json.JSONDecodeError, TypeError):
        return wiki_page_body

    parts: List[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "text" and "text" in node:
                parts.append(str(node["text"]))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def extract_wiki_body_from_unit(unit: Dict[str, Any]) -> str:
    """Достаёт wiki_page_body из ответа GET (attributes массив или объект)."""
    attrs = unit.get("attributes")
    if isinstance(attrs, list):
        for item in attrs:
            if not isinstance(item, dict):
                continue
            if item.get("code") == "wiki_page_body" or item.get("name") == "wiki_page_body":
                val = item.get("value")
                if isinstance(val, str):
                    return val
    if isinstance(attrs, dict) and "wiki_page_body" in attrs:
        v = attrs["wiki_page_body"]
        if isinstance(v, str):
            return v
    for key in ("wiki_page_body", "wikiPageBody"):
        v = unit.get(key)
        if isinstance(v, str):
            return v
    return ""
