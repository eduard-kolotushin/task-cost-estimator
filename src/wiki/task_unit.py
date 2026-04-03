"""Разбор ответа GET /rest/api/unit/v2/{code} (юнит задачи, не wiki-плагин)."""
from __future__ import annotations

import json
from typing import Any, Dict, List


def format_task_unit_for_prompt(unit: Dict[str, Any]) -> str:
    """
    Текст для промпта агента: summary, описание, атрибуты (без попытки парсить wiki_page_body как основной источник).
    """
    lines: List[str] = []
    code = unit.get("code") or unit.get("id")
    if code:
        lines.append(f"Код задачи: {code}")
    summary = unit.get("summary")
    if summary:
        lines.append(f"Заголовок: {summary}")
    for key in ("description", "descriptionPlain", "descriptionText"):
        v = unit.get(key)
        if v and str(v).strip():
            lines.append(f"Описание:\n{v}")
            break
    attrs = unit.get("attributes")
    if isinstance(attrs, list):
        for item in attrs:
            if not isinstance(item, dict):
                continue
            name = item.get("code") or item.get("name") or item.get("title") or ""
            val = item.get("value")
            if val is None:
                continue
            if isinstance(val, (dict, list)):
                val = json.dumps(val, ensure_ascii=False)
            elif isinstance(val, str) and len(val) > 8000:
                val = val[:8000] + "…"
            if name == "wiki_page_body" and isinstance(val, str) and len(val) > 400:
                lines.append(
                    f"Атрибут {name}: (длинное тело; для оценки используй summary/описание выше, при необходимости фрагмент)"
                )
                continue
            lines.append(f"Атрибут {name}: {val}")
    elif isinstance(attrs, dict):
        for k, v in attrs.items():
            if v is None:
                continue
            if isinstance(v, (dict, list)):
                v = json.dumps(v, ensure_ascii=False)
            lines.append(f"{k}: {v}")
    if not lines:
        return json.dumps(unit, ensure_ascii=False, indent=2)[:12000]
    return "\n\n".join(lines)
