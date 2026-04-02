# Агент оценки задач (TaskTracker wiki)

AI-агент на **Deep Agents** + **LangChain StructuredTools**: читает исходную wiki-страницу TaskTracker, декомпозирует работу и создаёт **новую** wiki-страницу с таблицей оценок (чел.-дни).

## Установка

```bash
pip install uv
cd task-estimation-agent
uv sync
```

Скопируйте шаблон и подставьте секреты:

```bash
# Windows
copy .env.example .env
# Linux / macOS
# cp .env.example .env
```

Файл `.env` в репозиторий не попадает (см. `.gitignore`).

## Переменные окружения

- **TaskTracker**: `TASKTRACKER_BASE_URL` (например `https://portal.works.prod.sbt/swtr`), `TASKTRACKER_TOKEN` и/или `TASKTRACKER_BASIC_AUTH` (`user:password`). Опционально `TASKTRACKER_DRY_RUN=true` — чтение/запись без реальных мутаций (создание возвращает фиктивный код).
- **Модель**: `LLM_MODEL` — по умолчанию `GigaChat-2`. Для семейства GigaChat нужны `GIGACHAT_API_KEY`, опционально `GIGACHAT_VERIFY_SSL`. Для других моделей через OpenAI-совместимый HUB: `HUB_BASE_URL`, `HUB_API_KEY`, `HUB_VERIFY_SSL`.
- **Пространство wiki**: `WIKI_SPACE` (по умолчанию `VIEW`).
- **Артефакты single-run**: `TASK_ESTIMATION_RUNS_DIR` (по умолчанию `runs`).
- Опционально: `POSTGRES_CHECKPOINT_URL`, `POSTGRES_STORE_URL` для персистентности LangGraph.

## Запуск

Интерактивно:

```bash
uv run python -m src.main --interactive
```

Один прогон по коду wiki:

```bash
uv run python -m src.main single-run --wiki-code VIEW-9150
```

С дополнительным текстом:

```bash
uv run python -m src.main single-run --wiki-code VIEW-9150 --prompt "Уточни риски интеграции."
```

Артефакты: `runs/<run-id>/plan.md`, `created_wiki.json`.

## Навык Deep Agents

Каталог `skills/` подключён в `build_agent()` как `/skills/`. Правила оценки и колонок таблицы — в [skills/task-cost-estimation/SKILL.md](skills/task-cost-estimation/SKILL.md).

## Примечание по таблице в wiki

Тело страницы — JSON ProseMirror (`wiki_page_body`). Таблица собирается с узлами `table` / `tableRow` / `tableCell` (TipTap-стиль). Если портал ожидает другие имена узлов, скорректируйте `src/wiki/prose.py` по ответу GET с реальной страницы с таблицей.
