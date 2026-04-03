"""Разбор и сборка ProseMirror JSON для wiki_page_body.

Схема узлов/атрибутов ориентирована на реальный ответ API (см. example_wiki_page_est_table.txt):
table с id/tableId/columnWidths, tableRow с originalRowIndex, tableCell с numberedColumn и т.д.
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Any, Dict, List, Optional

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


def _nid() -> str:
    return str(uuid.uuid4())


def _indent_attr() -> Any:
    """Как в примере портала: чаще объект, иногда число — в ячейках используем объект."""
    return {"indent": 0}


def _paragraph_block(
    text: str,
    *,
    bold: bool = False,
    text_align: str = "justify",
    indent_simple: bool = False,
) -> Dict[str, Any]:
    """Параграф внутри ячейки; bold через marks как в example_wiki_page_est_table.txt."""
    ind: Any = 0 if indent_simple else _indent_attr()
    node: Dict[str, Any] = {
        "type": "paragraph",
        "attrs": {
            "id": _nid(),
            "indent": ind,
            "textAlign": text_align,
        },
    }
    if not text:
        return node
    text_node: Dict[str, Any] = {"type": "text", "text": text}
    if bold:
        text_node["marks"] = [{"type": "bold"}]
    node["content"] = [text_node]
    return node


def _empty_paragraph_before_table() -> Dict[str, Any]:
    """Пустой абзац перед таблицей, как в примере из wiki."""
    return {
        "type": "paragraph",
        "attrs": {
            "id": _nid(),
            "indent": 0,
            "textAlign": "justify",
        },
    }


def _table_attrs(*, num_columns: int) -> Dict[str, Any]:
    """Атрибуты table из example_wiki_page_est_table.txt (адаптация под число колонок)."""
    base = 281
    widths = [base] * num_columns
    return {
        "id": _nid(),
        "tableId": _nid(),
        "columnWidths": widths,
        "filters": [],
        "sort": None,
        "summaryRow": {},
        "calcColumn": None,
        "style": None,
        "numberedActive": False,
        "hasHeaderRow": None,
        "hasHeaderColumn": None,
    }


def _row_attrs(original_row_index: int) -> Dict[str, Any]:
    return {
        "id": _nid(),
        "originalRowIndex": original_row_index,
        "filterHidden": False,
        "readOnly": None,
    }


def _cell_attrs(*, colspan: int = 1, rowspan: int = 1, background_color: Optional[str] = None) -> Dict[str, Any]:
    attrs: Dict[str, Any] = {
        "id": _nid(),
        "colspan": colspan,
        "rowspan": rowspan,
        "colwidth": None,
        "backgroundColor": background_color,
        "numberedColumn": {"numberedColumn": False},
    }
    return attrs


def _table_cell(
    *paragraphs: Dict[str, Any],
    colspan: int = 1,
    rowspan: int = 1,
    background_color: Optional[str] = None,
) -> Dict[str, Any]:
    content = list(paragraphs)
    return {
        "type": "tableCell",
        "attrs": _cell_attrs(colspan=colspan, rowspan=rowspan, background_color=background_color),
        "content": content,
    }


def _header_cells(labels: List[str]) -> Dict[str, Any]:
    """Первая строка: жирные заголовки, выравнивание как в примере (центр для оценки)."""
    aligns = ["justify", "justify", "justify", "center", "left"]
    cells = []
    for i, label in enumerate(labels):
        ta = aligns[i] if i < len(aligns) else "justify"
        cells.append(
            _table_cell(
                _paragraph_block(label, bold=True, text_align=ta),
                colspan=1,
                rowspan=1,
            )
        )
    return {
        "type": "tableRow",
        "attrs": _row_attrs(0),
        "content": cells,
    }


def _data_row(cells_text: List[str], row_index: int) -> Dict[str, Any]:
    """Обычная строка данных: пять ячеек."""
    paras: List[Dict[str, Any]] = []
    for i, t in enumerate(cells_text):
        ta = "justify"
        if i == 3:
            ta = "justify"
        paras.append(_table_cell(_paragraph_block(t, bold=False, text_align=ta, indent_simple=True)))
    return {
        "type": "tableRow",
        "attrs": _row_attrs(row_index),
        "content": paras,
    }


def build_estimation_doc(rows: List[EstimationRow]) -> Dict[str, Any]:
    """
    Документ с таблицей 5×(1+N): заголовок + строки.
    Структура узлов согласована с example_wiki_page_est_table.txt (атрибуты table/row/cell).
    """
    headers = ["Команда", "Компонент", "Этап", "Оценка", "Комментарий"]
    num_cols = len(headers)

    table_rows: List[Dict[str, Any]] = [_header_cells(headers)]

    for idx, r in enumerate(rows, start=1):
        otsenka_str = str(r.otsenka) if r.otsenka == int(r.otsenka) else str(round(r.otsenka, 2))
        table_rows.append(
            _data_row(
                [
                    r.komanda.strip(),
                    r.komponent.strip(),
                    r.etap.strip(),
                    otsenka_str,
                    r.kommentariy.strip(),
                ],
                row_index=idx,
            )
        )

    table_node: Dict[str, Any] = {
        "type": "table",
        "attrs": _table_attrs(num_columns=num_cols),
        "content": table_rows,
    }

    doc_content: List[Dict[str, Any]] = [
        _empty_paragraph_before_table(),
        table_node,
        {
            "type": "paragraph",
            "attrs": {
                "id": _nid(),
                "indent": 0,
                "textAlign": "justify",
            },
        },
    ]

    return {"type": "doc", "content": doc_content}


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
    for key in ("wiki_page_body", "wikiPageBody"):
        v = unit.get(key)
        if isinstance(v, str):
            return v
    return ""
