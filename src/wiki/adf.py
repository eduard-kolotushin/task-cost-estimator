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
_COL_WIDTHS = [280, 110, 280]

# В результирующей таблице wiki всегда выводятся все четыре блока.
CANONICAL_KOMANDA_ORDER = (
    "Аналитика/Проектирование",
    "Разработка",
    "Тестирование",
    "Документирование",
)

# Фиксированный набор этапов внутри каждой секции (как в QA.rtf / SKILL); порядок строк — как здесь.
CANONICAL_ETAPY_BY_KOMANDA: Dict[str, tuple[str, ...]] = {
    "Аналитика/Проектирование": (
        "Проектирование UI",
        "Тех. проектирование",
        "Прототип/RND",
    ),
    "Разработка": (
        "Разработка ПМИ/Наполнение тестовой модели",
        "Разработка (UI)",
        "Разработка (Back)",
        "Разработка (DevOps)",
        "Отладка и DEV-тестирование",
        "Внутрикомандное демо и исправления по замечаниям",
    ),
    "Тестирование": (
        "Ручное тестирование (ST, IFT)",
        "Разработка и прогон автотестов (ST, IFT)",
    ),
    "Документирование": ("Документирование",),
}


def _nid() -> str:
    return str(uuid.uuid4())


def _join_dekompozitsiya(a: str, b: str) -> str:
    a, b = (a or "").strip(), (b or "").strip()
    if not a:
        return b
    if not b:
        return a
    return f"{a}\n{b}"


def _merge_rows_same_etap(rows: List[EstimationRow]) -> EstimationRow:
    """Суммирует otsenka и склеивает dekompozitsiya для одинакового этапа."""
    first = rows[0]
    if len(rows) == 1:
        return first
    total = sum(r.otsenka for r in rows)
    text = rows[0].dekompozitsiya
    for r in rows[1:]:
        text = _join_dekompozitsiya(text, r.dekompozitsiya)
    return EstimationRow(
        komanda=first.komanda,
        komponent=first.komponent,
        etap=first.etap.strip(),
        otsenka=total,
        dekompozitsiya=text,
    )


def _partition_rows(
    rows: List[EstimationRow],
) -> tuple[Dict[str, List[EstimationRow]], List[str], Dict[str, List[EstimationRow]]]:
    """Строки по каноническим komanda; неизвестные ключи — в конец (порядок первого появления)."""
    canonical: Dict[str, List[EstimationRow]] = {k: [] for k in CANONICAL_KOMANDA_ORDER}
    extras: Dict[str, List[EstimationRow]] = {}
    extra_order: List[str] = []
    for r in rows:
        k = r.komanda.strip()
        if k in canonical:
            canonical[k].append(r)
        else:
            if k not in extras:
                extra_order.append(k)
                extras[k] = []
            extras[k].append(r)
    return canonical, extra_order, extras


def order_estimation_rows_for_wiki_table(rows: List[EstimationRow]) -> List[EstimationRow]:
    """
    Порядок строк для совместимости: сначала все канонические секции (в фиксированном порядке),
    затем нестандартные komanda (порядок первого появления).
    """
    canonical, extra_order, extras = _partition_rows(rows)
    out: List[EstimationRow] = []
    for k in CANONICAL_KOMANDA_ORDER:
        out.extend(canonical[k])
    for k in extra_order:
        out.extend(extras[k])
    return out


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


def _section_row(title: str, ri: int) -> Dict[str, Any]:
    return {
        "type": "tableRow",
        "attrs": _table_row_attrs(ri),
        "content": [
            _cell([_paragraph_text(title, bold=True, align="center")], colspan=3),
        ],
    }


def _data_row(r: EstimationRow, ri: int) -> Dict[str, Any]:
    otsenka_str = str(r.otsenka) if r.otsenka == int(r.otsenka) else str(round(r.otsenka, 2))
    raw_d = (r.dekompozitsiya or "").strip()
    if not raw_d:
        decomp_content: List[Dict[str, Any]] = [_paragraph_empty()]
    else:
        lines = decomposition_lines_from_text(r.dekompozitsiya)
        decomp_content = [_ordered_list(lines)] if lines else [_paragraph_empty()]
    return {
        "type": "tableRow",
        "attrs": _table_row_attrs(ri),
        "content": [
            _cell([_paragraph_text(r.etap.strip(), align="justify")]),
            _cell([_paragraph_text(otsenka_str, align="center")]),
            _cell(decomp_content),
        ],
    }


def _index_rows_by_etap(
    section_rows: List[EstimationRow], canonical_etaps: tuple[str, ...]
) -> tuple[Dict[str, List[EstimationRow]], List[EstimationRow]]:
    """Строки с этапом из справочника — по точному имени; остальные — в хвост секции."""
    by_etap: Dict[str, List[EstimationRow]] = {e: [] for e in canonical_etaps}
    unknown: List[EstimationRow] = []
    canon_set = set(canonical_etaps)
    for r in section_rows:
        e = r.etap.strip()
        if e in canon_set:
            by_etap[e].append(r)
        else:
            unknown.append(r)
    return by_etap, unknown


def _build_table(rows: List[EstimationRow]) -> Dict[str, Any]:
    canonical, extra_order, extras = _partition_rows(list(rows))
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

    for title in CANONICAL_KOMANDA_ORDER:
        body_rows.append(_section_row(title, ri))
        ri += 1
        etapy = CANONICAL_ETAPY_BY_KOMANDA[title]
        by_etap, unknown = _index_rows_by_etap(canonical[title], etapy)
        for etap in etapy:
            bucket = by_etap[etap]
            if bucket:
                merged = _merge_rows_same_etap(bucket)
            else:
                merged = EstimationRow(
                    komanda=title,
                    komponent="VIEW",
                    etap=etap,
                    otsenka=0,
                    dekompozitsiya="",
                )
            body_rows.append(_data_row(merged, ri))
            ri += 1
        for r in unknown:
            body_rows.append(_data_row(r, ri))
            ri += 1

    for title in extra_order:
        body_rows.append(_section_row(title, ri))
        ri += 1
        for r in extras[title]:
            body_rows.append(_data_row(r, ri))
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
    """Документ TipTap: doc → пустой абзац, таблица, пустой абзац (как в example_wiki_page_est_table.txt).

    `rows` может быть пустым — таблица всё равно строится по полной сетке этапов (нули).
    """
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
