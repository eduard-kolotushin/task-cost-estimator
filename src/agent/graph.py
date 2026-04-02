"""Сборка Deep Agent с инструментами wiki."""
from __future__ import annotations

from typing import Any, Dict, Optional, Set

import httpx
from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend, StateBackend, StoreBackend
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command
from langchain_openai import ChatOpenAI

from src.agent.prompts import SYSTEM_PROMPT
from src.agent.tools import all_tools
from src.config import (
    get_gigachat_credentials,
    get_gigachat_verify_ssl,
    get_hub_api_key,
    get_hub_base_url,
    get_hub_verify_ssl,
    get_model_name,
    get_postgres_checkpoint_url,
    get_postgres_store_url,
)

GIGACHAT_MODELS: Set[str] = {"GigaChat-2", "GigaChat-2-Pro", "GigaChat-2-Max"}

_CHECKPOINTER_CM: Optional[Any] = None
_CHECKPOINTER: Optional[Any] = None
_STORE_CM: Optional[Any] = None
_STORE: Optional[Any] = None


def _build_gigachat_model(model_name: str) -> Any:
    try:
        from langchain_gigachat import GigaChat
    except ImportError as e:
        raise RuntimeError(
            "Для моделей GigaChat установите зависимость: pip install langchain-gigachat "
            "или uv sync с extra gigachat"
        ) from e
    return GigaChat(
        model=model_name,
        credentials=get_gigachat_credentials(),
        verify_ssl_certs=get_gigachat_verify_ssl(),
        scope="GIGACHAT_API_CORP",
        timeout=(10.0 * 60),
    )


def build_hub_model(model_name: str) -> ChatOpenAI:
    base_url = get_hub_base_url()
    api_key = get_hub_api_key()
    verify = get_hub_verify_ssl()
    http_client = httpx.Client(verify=verify, timeout=600.0)
    return ChatOpenAI(
        model=model_name,
        base_url=base_url,
        api_key=api_key,
        http_client=http_client,
        timeout=600,
    )


def build_checkpointer() -> Any:
    global _CHECKPOINTER_CM, _CHECKPOINTER

    dsn = get_postgres_checkpoint_url()
    if not dsn:
        return InMemorySaver()

    if _CHECKPOINTER is not None:
        return _CHECKPOINTER

    try:
        from langgraph.checkpoint.postgres import PostgresSaver  # type: ignore[import]
    except ImportError:
        return InMemorySaver()

    _CHECKPOINTER_CM = PostgresSaver.from_conn_string(dsn)
    _CHECKPOINTER = _CHECKPOINTER_CM.__enter__()
    _CHECKPOINTER.setup()
    return _CHECKPOINTER


def build_store() -> Any:
    global _STORE_CM, _STORE

    dsn = get_postgres_store_url()
    if not dsn:
        return InMemoryStore()

    if _STORE is not None:
        return _STORE

    try:
        from langgraph.store.postgres import PostgresStore  # type: ignore[import]
    except ImportError:
        return InMemoryStore()

    _STORE_CM = PostgresStore.from_conn_string(dsn)
    _STORE = _STORE_CM.__enter__()
    _STORE.setup()
    return _STORE


def build_backend() -> Any:
    def factory(runtime: Any) -> Any:
        return CompositeBackend(
            default=StateBackend(runtime),
            routes={
                "/memories/": StoreBackend(runtime),
                "/skills/": FilesystemBackend(root_dir="./skills", virtual_mode=True),
            },
        )

    return factory


def build_model() -> Any:
    model_name = get_model_name()
    if model_name in GIGACHAT_MODELS:
        return _build_gigachat_model(model_name)
    return build_hub_model(model_name)


def build_agent() -> Any:
    tools = all_tools()
    model = build_model()
    checkpointer = build_checkpointer()
    backend = build_backend()
    store = build_store()

    return create_deep_agent(
        model=model,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        skills=["/skills/"],
        checkpointer=checkpointer,
        backend=backend,
        store=store,
        interrupt_on={
            "create_wiki_page_estimation": True,
            "update_wiki_page": True,
        },
    )


def run_once(agent: Any, user_message: str, thread_id: Optional[str] = None) -> Dict[str, Any]:
    payload = {
        "messages": [
            {"role": "user", "content": user_message},
        ]
    }
    if thread_id:
        config = {"configurable": {"thread_id": thread_id}}
        return agent.invoke(payload, config)
    return agent.invoke(payload)


def run_until_done(
    agent: Any,
    payload: Dict[str, Any],
    config: Dict[str, Any],
    *,
    auto_approve: bool = False,
) -> Dict[str, Any]:
    """Запуск агента до снятия interrupt (при auto_approve — одобрить вызовы инструментов)."""
    result = agent.invoke(payload, config)
    while result.get("__interrupt__") and auto_approve:
        interrupts = result["__interrupt__"][0].value
        action_requests = interrupts["action_requests"]
        decisions = [{"type": "approve"} for _ in action_requests]
        result = agent.invoke(
            Command(resume={"decisions": decisions}),
            config=config,
        )
    return result
