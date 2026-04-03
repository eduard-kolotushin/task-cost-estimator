"""HTTP-клиент для wiki API TaskTracker."""
from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx

from src.config import (
    get_tasktracker_base_url,
    get_tasktracker_basic_auth,
    get_tasktracker_dry_run,
    get_tasktracker_token,
    get_wiki_space_default,
)


@dataclass
class WikiClient:
    base_url: str
    token: Optional[str] = None
    basic_auth: Optional[str] = None
    dry_run: bool = False
    timeout: float = 300.0

    def __post_init__(self) -> None:
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
            headers=self._build_headers(),
            verify=False,
        )

    @classmethod
    def from_env(cls) -> "WikiClient":
        return cls(
            base_url=get_tasktracker_base_url(),
            token=get_tasktracker_token(),
            basic_auth=get_tasktracker_basic_auth(),
            dry_run=get_tasktracker_dry_run(),
        )

    def _build_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
        }
        if self.basic_auth:
            raw = self.basic_auth.encode("utf-8")
            b64 = base64.b64encode(raw).decode("ascii")
            headers["Authorization"] = f"Basic {b64}"
        elif self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def get_wiki_unit(self, code: str) -> Dict[str, Any]:
        """
        GET /extension/plugin/v2/rest/api/swtr_wiki_plugin/v2/wiki/unit/{code}
        """
        if self.dry_run:
            return {
                "code": code,
                "summary": "[dry-run] Заголовок",
                "description": "",
                "attributes": {
                    "wiki_page_body": _minimal_doc_json("Текст задачи в dry-run."),
                },
            }
        path = f"/extension/plugin/v2/rest/api/swtr_wiki_plugin/v2/wiki/unit/{code}"
        response = self._client.get(path)
        response.raise_for_status()
        return response.json()

    def create_wiki_page(
        self,
        *,
        summary: str,
        space: str,
        description: str = "",
        wiki_page_body: str,
        label: Optional[list] = None,
    ) -> Dict[str, Any]:
        """
        POST /rest/api/unit/v2/wiki_page/create
        """
        body: Dict[str, Any] = {
            "summary": summary,
            "space": space,
            "description": description,
            "attributes": {
                "watchers": [],
                "wiki_page_body": wiki_page_body,
                "label": label if label is not None else [],
            },
        }
        if self.dry_run:
            return {
                "code": "VIEW-DRYRUN-1",
                "summary": summary,
                "space": space,
                "dry_run": True,
                "request_body_preview": {k: v for k, v in body.items() if k != "attributes"},
            }
        response = self._client.post(
            "/rest/api/unit/v2/wiki_page/create",
            json=body,
        )
        response.raise_for_status()
        return response.json()

    def update_wiki_unit(
        self,
        code: str,
        *,
        wiki_page_body: str,
    ) -> Dict[str, Any]:
        """
        PATCH /rest/api/unit/v2/update/{code}
        """
        body = {"attributes": {"wiki_page_body": wiki_page_body}}
        if self.dry_run:
            return {"code": code, "dry_run": True, "patched": True}
        path = f"/rest/api/unit/v2/update/{code}"
        response = self._client.patch(path, json=body)
        response.raise_for_status()
        return response.json()

    def get_wiki_hierarchy(
        self,
        *,
        spaces: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        """
        POST .../swtr_wiki_plugin/v1/wiki/unit/hierarchy

        root всегда null — полное дерево в указанных пространствах.
        """
        space_list = spaces if spaces else [get_wiki_space_default()]
        body: Dict[str, Any] = {
            "param": {"eager": False, "root": None},
            "filter": {"spaces": space_list},
            "sort": {"type": "rank", "direction": "ASC"},
        }
        if self.dry_run:
            return {
                "dry_run": True,
                "spaces": space_list,
                "hierarchy_preview": [],
            }
        path = "/extension/plugin/v2/rest/api/swtr_wiki_plugin/v1/wiki/unit/hierarchy"
        response = self._client.post(path, json=body)
        response.raise_for_status()
        return response.json()

    def link_wiki_parent_child(self, parent: str, child: str) -> Dict[str, Any]:
        """
        PATCH .../swtr_wiki_plugin/v1/wiki/unit/hierarchy/link

        Сделать страницу child дочерней для parent.
        """
        body = {"parent": parent.strip(), "child": child.strip()}
        if self.dry_run:
            return {"dry_run": True, **body, "linked": True}
        path = "/extension/plugin/v2/rest/api/swtr_wiki_plugin/v1/wiki/unit/hierarchy/link"
        response = self._client.patch(path, json=body)
        response.raise_for_status()
        return response.json()


def _minimal_doc_json(text: str) -> str:
    import json

    doc = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "attrs": {
                    "id": "00000000-0000-4000-8000-000000000001",
                    "indent": 0,
                    "textAlign": "justify",
                },
                "content": [{"type": "text", "text": text}],
            }
        ],
    }
    return json.dumps(doc, ensure_ascii=False)
