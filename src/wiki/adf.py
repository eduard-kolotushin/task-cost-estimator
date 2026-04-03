"""Сборка ADF для wiki_page_body через atlassian-doc-builder.

Структура таблицы как в example_wiki_page_est_table.txt: заголовок колонок → строки-секции
(одна ячейка на всю ширину с названием блока «Команда») → строки данных → строка «Итого».
В колонке «Декомпозиция» — нумерованный список (orderedList).
"""
from __future__ import annotations

import json
import re
from typing import Dict, List

from atlassian_doc_builder import (
    ADFDoc,
    ADFListItem,
    ADFOrderList,
    ADFParagraph,
    ADFStrong,
    ADFTable,
    ADFTableRow,
    ADFText,
)

from src.wiki.prose import EstimationRow

_TABLE_HEADERS = ["Команда", "Компонент", "Этап", "Оценка", "Декомпозиция"]


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
    Разбивает текст поля dekompozitsiya на пункты нумерованного списка.
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


def _paragraph_plain(text: str) -> ADFParagraph:
    p = ADFParagraph()
    p.add(ADFText(text if text else " "))
    return p


def _paragraph_strong(text: str) -> ADFParagraph:
    p = ADFParagraph()
    t = ADFText(text)
    t.add(ADFStrong())
    p.add(t)
    return p


def _cell_set_paragraph(cell, paragraph: ADFParagraph) -> None:
    cell.extend_content([paragraph])


def _cell_set_ordered_list(cell, lines: List[str]) -> None:
    ol = ADFOrderList()
    for line in lines:
        li = ADFListItem()
        li.extend_content([_paragraph_plain(line)])
        ol.extend_content([li])
    cell.extend_content([ol])


def _build_header_row() -> ADFTableRow:
    row = ADFTableRow.create(dimension=5, is_header=True)
    for j, title in enumerate(_TABLE_HEADERS):
        _cell_set_paragraph(row[j], _paragraph_strong(title))
    return row


def _build_section_row(section_title: str) -> ADFTableRow:
    """Одна ячейка colspan=5 — как блок «Аналитика/Проектирование» в примере wiki."""
    row = ADFTableRow.create(spanned_layout=[5])
    _cell_set_paragraph(row[0], _paragraph_strong(section_title.strip()))
    return row


def _build_data_row(r: EstimationRow) -> ADFTableRow:
    """Строка данных: колонка «Команда» пустая — блок уже в строке-секции выше."""
    row = ADFTableRow.create(dimension=5, is_header=False)
    otsenka_str = str(r.otsenka) if r.otsenka == int(r.otsenka) else str(round(r.otsenka, 2))
    _cell_set_paragraph(row[0], _paragraph_plain(" "))
    _cell_set_paragraph(row[1], _paragraph_plain(r.komponent.strip()))
    _cell_set_paragraph(row[2], _paragraph_plain(r.etap.strip()))
    _cell_set_paragraph(row[3], _paragraph_plain(otsenka_str))
    lines = decomposition_lines_from_text(r.dekompozitsiya)
    _cell_set_ordered_list(row[4], lines)
    return row


def _build_total_row(total: float) -> ADFTableRow:
    row = ADFTableRow.create(dimension=5, is_header=False)
    tot = str(int(total)) if total == int(total) else str(round(total, 2))
    _cell_set_paragraph(row[0], _paragraph_strong("Итого"))
    _cell_set_paragraph(row[1], _paragraph_plain(" "))
    _cell_set_paragraph(row[2], _paragraph_plain(" "))
    _cell_set_paragraph(row[3], _paragraph_plain(tot))
    _cell_set_paragraph(row[4], _paragraph_plain(" "))
    return row


def build_estimation_adf_doc(rows: List[EstimationRow]) -> dict:
    """Таблица с секциями по полю «Команда» и итоговой строкой."""
    if not rows:
        raise ValueError("rows не может быть пустым")

    rows = order_estimation_rows_for_wiki_table(list(rows))

    table_rows: List = [_build_header_row()]

    prev_komanda: str | None = None
    for r in rows:
        k = r.komanda.strip()
        if k != prev_komanda:
            table_rows.append(_build_section_row(k))
            prev_komanda = k
        table_rows.append(_build_data_row(r))

    total = sum(r.otsenka for r in rows)
    table_rows.append(_build_total_row(total))

    table = ADFTable()
    table.extend_content(table_rows)
    table.assign_info(
        "attrs",
        isNumberColumnEnabled=False,
        layout="center",
        displayMode="default",
        width=1200,
    )

    doc = ADFDoc()
    doc.extend_content([table])
    return doc.render()


def build_estimation_wiki_body(rows: List[EstimationRow]) -> str:
    """Строка JSON для attributes.wiki_page_body (ADF)."""
    return json.dumps(build_estimation_adf_doc(rows), ensure_ascii=False)


def minimal_adf_doc_json(text: str) -> str:
    """Минимальный ADF-документ (один абзац) для dry-run и тестов."""
    doc = ADFDoc()
    doc.extend_content([_paragraph_plain(text)])
    return json.dumps(doc.render(), ensure_ascii=False)
