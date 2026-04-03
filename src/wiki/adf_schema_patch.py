"""Патч загрузки ADF-схемы в atlassian-doc-builder.

Пакет тянет JSON-схему с https://unpkg.com/... через urllib.request.urlopen.
В средах без доверенных корневых сертификатов (macOS Python, корпоративный SSL)
это даёт SSL: CERTIFICATE_VERIFY_FAILED. Подменяем adf_schema на загрузку с
fallback на ssl._create_unverified_context() при ошибке проверки сертификата.
"""
from __future__ import annotations

import json
import logging
import ssl
import urllib.error
import urllib.request
from functools import lru_cache as cache

log = logging.getLogger(__name__)


def apply_patch() -> None:
    import atlassian_doc_builder.adf_object as ado

    default_url = ado.DEFAULT_SCHEMA_URL

    @cache
    def adf_schema(schema_url: str | None = None):
        if schema_url is None:
            schema_url = default_url
        req = urllib.request.Request(schema_url)
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                return json.load(response)
        except urllib.error.URLError as e:
            reason = getattr(e, "reason", None)
            if isinstance(reason, ssl.SSLCertVerificationError):
                log.warning(
                    "ADF schema: SSL verify failed (%s), retrying without certificate verification (unpkg.com)",
                    reason,
                )
                ctx = ssl._create_unverified_context()
                with urllib.request.urlopen(req, context=ctx, timeout=120) as response:
                    return json.load(response)
            raise

    ado.adf_schema = adf_schema
