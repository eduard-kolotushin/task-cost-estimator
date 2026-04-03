"""Модель строки оценки и извлечение текста из wiki_page_body (ADF / JSON с узлами text)."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from pydantic import BaseModel, Field, field_validator


class EstimationRow(BaseModel):
    """Строка таблицы оценок (чел.-дни)."""

    komanda: str = Field(
        ...,
        description="Блок из справочника: Аналитика/Проектирование | Разработка | Тестирование | Документирование (одинаковый для всех строк одной секции)",
    )
    komponent: str = Field(default="VIEW", description="Всегда VIEW")
    etap: str = Field(..., description="Точное имя этапа из справочника навыка (одна строка таблицы = один этап)")
    otsenka: float = Field(
        ...,
        ge=0,
        description="Итог по строке в чел.-днях; должно совпадать с суммой оценок в dekompozitsiya",
    )
    dekompozitsiya: str = Field(
        ...,
        description=(
            "Декомпозиция работ для этой строки: несколько строк текста (\\n). "
            "Каждая строка станет пунктом нумерованного списка в wiki; укажи подзадачи с оценкой в чел.-днях и при необходимости строку «Обоснование: …». "
            "Сервер превращает это в orderedList в колонке «Декомпозиция»."
        ),
    )

    @field_validator("komponent")
    @classmethod
    def component_view(cls, v: str) -> str:
        if v.strip().upper() != "VIEW":
            return "VIEW"
        return "VIEW"


def extract_text_from_wiki_body(wiki_page_body: str) -> str:
    """Рекурсивно извлекает текст из JSON тела wiki (ADF или совместимого дерева) для передачи в LLM."""
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
