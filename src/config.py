"""Конфигурация из переменных окружения (по аналогии с ui-test-generator)."""
from __future__ import annotations

import os
from typing import Optional


def _get_bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y"}


def get_gigachat_credentials() -> str:
    value = os.getenv("GIGACHAT_API_KEY")
    if not value:
        raise RuntimeError("GIGACHAT_API_KEY не задан.")
    return value


def get_gigachat_verify_ssl() -> bool:
    return _get_bool_env("GIGACHAT_VERIFY_SSL", default=False)


def get_tasktracker_base_url() -> str:
    value = os.getenv("TASKTRACKER_BASE_URL")
    if not value:
        raise RuntimeError(
            "TASKTRACKER_BASE_URL не задан. Пример: https://portal.works.prod.sbt/swtr"
        )
    return value.rstrip("/")


def get_tasktracker_token() -> Optional[str]:
    return os.getenv("TASKTRACKER_TOKEN")


def get_tasktracker_basic_auth() -> Optional[str]:
    return os.getenv("TASKTRACKER_BASIC_AUTH")


def get_tasktracker_dry_run() -> bool:
    return _get_bool_env("TASKTRACKER_DRY_RUN", default=False)


def get_postgres_checkpoint_url() -> Optional[str]:
    return os.getenv("POSTGRES_CHECKPOINT_URL")


def get_postgres_store_url() -> Optional[str]:
    return os.getenv("POSTGRES_STORE_URL")


def get_model_name() -> str:
    return os.getenv("LLM_MODEL", "GigaChat-2")


def get_hub_base_url() -> str:
    value = os.getenv("HUB_BASE_URL")
    if not value:
        raise RuntimeError(
            "HUB_BASE_URL не задан. Пример: http://localhost:12434/v1"
        )
    return value.rstrip("/")


def get_hub_api_key() -> str:
    return os.getenv("HUB_API_KEY", "sk-local")


def get_hub_verify_ssl() -> bool:
    return _get_bool_env("HUB_VERIFY_SSL", default=True)


def get_wiki_space_default() -> str:
    return os.getenv("WIKI_SPACE", "VIEW")


def get_runs_dir() -> str:
    return os.getenv("TASK_ESTIMATION_RUNS_DIR", "runs")
