"""Сборка тела wiki_page_body в формате TipTap/ProseMirror.

Структура колонок и секций как в QA.rtf / example_wiki_page_est_table.txt: три колонки
**Этап | Оценка | Декомпозиция**, строки-секции по команде (colspan=3), строка **Итого**.
Поля `komanda` / `komponent` в данных строк не выводятся в таблицу (нужны для API и группировки).
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Any, Dict, List

from src.wiki.prose import EstimationRow

# Как в QA.rtf: Этап | Оценка | Декомпозиция (пропорции ширин близки к шаблону)
_TABLE_HEADERS = ["Этап", "Оценка", "Декомпозиция"]
_COL_WIDTHS = [280, 110, 280]


def _nid() -> str:
    return str(uuid.uuid4())


def order_estimation_rows_for_wiki_table(rows: List[EstimationRow]) -> List[EstimationRow]:
    """
    Группирует строки по «Команде» подряд: в wiki для каждого блока одна строка-секция,
    затем все строки этого блока. Порядок групп — по первому появлению komanda в исходном списке.
    """
    order_keys: List[str] = []
    buckets: Dict[str, List[EstimationRow]] = {}
    for r in rows:
        k = r.komanda.strip()
        if k not in buckets:
            buckets[k] = []
            order_keys.append(k)
        buckets[k].append(r)
    return [r for k in order_keys for r in buckets[k]]


def decomposition_lines_from_text(raw: str) -> List[str]:
    """
    Разбивает текст поля dekompozitsiya на пункты списка.
    Убирает ведущую нумерацию/маркеры строк («1. », «2) », «- »).
    """
    s = (raw or "").strip()
    if not s:
        return ["—"]
    lines: List[str] = []
    for line in s.splitlines():
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^\d+[\.\)]\s*", "", line)
        line = re.sub(r"^[-*•]\s+", "", line)
        if line:
            lines.append(line)
    return lines if lines else [s]


def _paragraph_empty(*, align: str = "justify") -> Dict[str, Any]:
    return {"type": "paragraph", "attrs": {"id": _nid(), "indent": 0, "textAlign": align}}


def _paragraph_text(text: str, *, bold: bool = False, align: str = "justify") -> Dict[str, Any]:
    node: Dict[str, Any] = {
        "type": "paragraph",
        "attrs": {"id": _nid(), "indent": 0, "textAlign": align},
    }
    t: Dict[str, Any] = {"type": "text", "text": text if text else " "}
    if bold:
        t["marks"] = [{"type": "bold"}]
    node["content"] = [t]
    return node


def _table_row_attrs(original_index: int) -> Dict[str, Any]:
    return {
        "id": _nid(),
        "originalRowIndex": original_index,
        "filterHidden": False,
        "readOnly": None,
    }


def _table_cell_attrs(*, colspan: int = 1, rowspan: int = 1) -> Dict[str, Any]:
    return {
        "id": _nid(),
        "colspan": colspan,
        "rowspan": rowspan,
        "colwidth": None,
        "backgroundColor": None,
        "numberedColumn": {"numberedColumn": False},
    }


def _cell(content_blocks: List[Dict[str, Any]], *, colspan: int = 1, rowspan: int = 1) -> Dict[str, Any]:
    return {
        "type": "tableCell",
        "attrs": _table_cell_attrs(colspan=colspan, rowspan=rowspan),
        "content": content_blocks,
    }


def _ordered_list(lines: List[str]) -> Dict[str, Any]:
    items: List[Dict[str, Any]] = []
    for line in lines:
        items.append(
            {
                "type": "listItem",
                "content": [_paragraph_text(line, align="justify")],
            }
        )
    return {
        "type": "orderedList",
        "attrs": {"start": 1, "type": None},
        "content": items,
    }


def _build_table(rows: List[EstimationRow]) -> Dict[str, Any]:
    rows = order_estimation_rows_for_wiki_table(list(rows))
    table_id = _nid()
    body_rows: List[Dict[str, Any]] = []
    ri = 0

    header_cells: List[Dict[str, Any]] = [
        _cell([_paragraph_text("Этап", bold=True, align="justify")]),
        _cell([_paragraph_text("Оценка", bold=True, align="center")]),
        _cell([_paragraph_text("Декомпозиция", bold=True, align="justify")]),
    ]
    body_rows.append({"type": "tableRow", "attrs": _table_row_attrs(ri), "content": header_cells})
    ri += 1

    prev_komanda: str | None = None
    for r in rows:
        k = r.komanda.strip()
        if k != prev_komanda:
            body_rows.append(
                {
                    "type": "tableRow",
                    "attrs": _table_row_attrs(ri),
                    "content": [
                        _cell(
                            [_paragraph_text(k, bold=True, align="center")],
                            colspan=3,
                        )
                    ],
                }
            )
            ri += 1
            prev_komanda = k

        otsenka_str = str(r.otsenka) if r.otsenka == int(r.otsenka) else str(round(r.otsenka, 2))
        lines = decomposition_lines_from_text(r.dekompozitsiya)
        decomp_content: List[Dict[str, Any]] = [_ordered_list(lines)] if lines else [_paragraph_empty()]

        body_rows.append(
            {
                "type": "tableRow",
                "attrs": _table_row_attrs(ri),
                "content": [
                    _cell([_paragraph_text(r.etap.strip(), align="justify")]),
                    _cell([_paragraph_text(otsenka_str, align="center")]),
                    _cell(decomp_content),
                ],
            }
        )
        ri += 1

    total = sum(x.otsenka for x in rows)
    tot = str(int(total)) if total == int(total) else str(round(total, 2))
    body_rows.append(
        {
            "type": "tableRow",
            "attrs": _table_row_attrs(ri),
            "content": [
                _cell([_paragraph_text("Итого", bold=True, align="justify")]),
                _cell([_paragraph_text(tot, align="center")]),
                _cell([_paragraph_empty()]),
            ],
        }
    )

    return {
        "type": "table",
        "attrs": {
            "id": _nid(),
            "tableId": table_id,
            "columnWidths": _COL_WIDTHS,
            "filters": [],
            "sort": None,
            "summaryRow": {},
            "calcColumn": None,
            "style": None,
            "numberedActive": False,
            "hasHeaderRow": None,
            "hasHeaderColumn": None,
        },
        "content": body_rows,
    }


def build_estimation_wiki_doc(rows: List[EstimationRow]) -> Dict[str, Any]:
    """Документ TipTap: doc → пустой абзац, таблица, пустой абзац (как в example_wiki_page_est_table.txt)."""
    if not rows:
        raise ValueError("rows не может быть пустым")
    return {
        "type": "doc",
        "content": [
            _paragraph_empty(),
            _build_table(rows),
            _paragraph_empty(),
        ],
    }


def build_estimation_wiki_body(rows: List[EstimationRow]) -> str:
    """Строка JSON для attributes.wiki_page_body (TipTap/ProseMirror doc)."""
    return json.dumps(build_estimation_wiki_doc(rows), ensure_ascii=False)


def minimal_wiki_doc_json(text: str) -> str:
    """Минимальный doc (один абзац) для dry-run и тестов."""
    return json.dumps(
        {
            "type": "doc",
            "content": [_paragraph_text(text, align="justify")],
        },
        ensure_ascii=False,
    )


# Обратная совместимость имён
build_estimation_adf_doc = build_estimation_wiki_doc
minimal_adf_doc_json = minimal_wiki_doc_json
