"""Разбор и сборка ProseMirror JSON для wiki_page_body."""
from __future__ import annotations

import json
import re
import uuid
from typing import Any, Dict, List

from pydantic import BaseModel, Field, field_validator


class EstimationRow(BaseModel):
    """Строка таблицы оценок (чел.-дни)."""

    komanda: str = Field(..., description="Команда / роль")
    komponent: str = Field(default="VIEW", description="Всегда VIEW")
    etap: str = Field(..., description="Этап / фаза работ")
    otsenka: float = Field(..., ge=0, description="Итог по строке, чел.-дни")
    kommentariy: str = Field(
        ...,
        description="Декомпозиция с оценками подзадач (чел.-дни) и обоснование набора задач",
    )

    @field_validator("komponent")
    @classmethod
    def component_view(cls, v: str) -> str:
        if v.strip().upper() != "VIEW":
            return "VIEW"
        return "VIEW"


def _new_para_id() -> str:
    return str(uuid.uuid4())


def _paragraph_with_text(text: str) -> Dict[str, Any]:
    return {
        "type": "paragraph",
        "attrs": {
            "id": _new_para_id(),
            "indent": 0,
            "textAlign": "justify",
        },
        "content": [{"type": "text", "text": text}],
    }


def _cell_paragraph(text: str) -> Dict[str, Any]:
    """Ячейка таблицы (TipTap: tableCell)."""
    return {
        "type": "tableCell",
        "attrs": {
            "colspan": 1,
            "rowspan": 1,
            "colwidth": None,
        },
        "content": [_paragraph_with_text(text)],
    }


def _table_row(cells: List[str]) -> Dict[str, Any]:
    return {
        "type": "tableRow",
        "content": [_cell_paragraph(c) for c in cells],
    }


def build_estimation_doc(rows: List[EstimationRow]) -> Dict[str, Any]:
    """
    Собирает документ ProseMirror с таблицей 5×(1+N): заголовок + строки данных.
    Имена узлов совместимы с типичным @tiptap/extension-table / prosemirror-tables.
    """
    headers = ["Команда", "Компонент", "Этап", "Оценка", "Комментарий"]
    table_content: List[Dict[str, Any]] = [
        _table_row(headers),
    ]
    for r in rows:
        otsenka_str = str(r.otsenka) if r.otsenka == int(r.otsenka) else str(round(r.otsenka, 2))
        table_content.append(
            _table_row(
                [
                    r.komanda.strip(),
                    r.komponent.strip(),
                    r.etap.strip(),
                    f"{otsenka_str} чел.-дн.",
                    r.kommentariy.strip(),
                ]
            )
        )

    return {
        "type": "doc",
        "content": [
            {
                "type": "table",
                "content": table_content,
            }
        ],
    }


def build_estimation_wiki_body(rows: List[EstimationRow]) -> str:
    """Строка JSON для attributes.wiki_page_body."""
    doc = build_estimation_doc(rows)
    return json.dumps(doc, ensure_ascii=False)


def extract_text_from_wiki_body(wiki_page_body: str) -> str:
    """Рекурсивно извлекает текст из JSON тела wiki для передачи в LLM."""
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
    # Плоский ключ на юните
    for key in ("wiki_page_body", "wikiPageBody"):
        v = unit.get(key)
        if isinstance(v, str):
            return v
    return ""
