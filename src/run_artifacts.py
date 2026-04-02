"""Артефакты single-run: план, созданные wiki-операции."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def create_run_dir(output_dir: str | Path, run_id: str) -> Path:
    path = Path(output_dir) / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_plan(run_dir: Path, content: str) -> Path:
    out = run_dir / "plan.md"
    out.write_text(content, encoding="utf-8")
    return out


def write_created_wiki(run_dir: Path, items: List[Dict[str, Any]]) -> Path:
    out = run_dir / "created_wiki.json"
    out.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def write_failure_reason(run_dir: Path, content: str) -> Path:
    out = run_dir / "failure_reason.txt"
    out.write_text(content, encoding="utf-8")
    return out


def _message_content(msg: Any) -> Any:
    if isinstance(msg, dict):
        return msg.get("content")
    return getattr(msg, "content", None)


def _message_tool_calls(msg: Any) -> List[Dict[str, Any]]:
    if isinstance(msg, dict):
        return msg.get("tool_calls") or msg.get("additional_kwargs", {}).get("tool_calls") or []
    return getattr(msg, "tool_calls", None) or []


def _message_tool_call_id(msg: Any) -> Any:
    if isinstance(msg, dict):
        return msg.get("tool_call_id")
    return getattr(msg, "tool_call_id", None)


def _message_type(msg: Any) -> str:
    if isinstance(msg, dict):
        return str(msg.get("type", ""))
    return type(msg).__name__


def extract_plan_from_result(result: Dict[str, Any]) -> str:
    messages = result.get("messages") or []
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        kind = _message_type(msg)
        if kind in ("AIMessage", "ai"):
            content = _message_content(msg)
            if isinstance(content, str) and content.strip():
                return content
            if isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text", "")
                        if isinstance(text, str) and text.strip():
                            parts.append(text)
                if parts:
                    return "\n\n".join(parts)
            break
    return ""


def extract_wiki_tool_calls_from_result(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Собирает вызовы create_wiki_page_estimation и update_wiki_page с результатами."""
    messages = result.get("messages") or []
    tool_results: Dict[str, Any] = {}
    for msg in messages:
        if _message_type(msg) not in ("ToolMessage", "tool"):
            continue
        tid = _message_tool_call_id(msg)
        if tid is not None:
            content = _message_content(msg)
            if isinstance(content, str) and content.strip():
                try:
                    content = json.loads(content)
                except (json.JSONDecodeError, TypeError):
                    pass
            tool_results[tid] = content

    created: List[Dict[str, Any]] = []
    for msg in messages:
        if _message_type(msg) not in ("AIMessage", "ai"):
            continue
        for tc in _message_tool_calls(msg):
            name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
            if name not in ("create_wiki_page_estimation", "update_wiki_page"):
                continue
            args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {}) or {}
            tid = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
            result_content = tool_results.get(tid) if tid else None
            created.append({
                "tool": name,
                "args": args,
                "result": result_content,
            })
    return created
