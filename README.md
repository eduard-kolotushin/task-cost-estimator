# Агент оценки задач (TaskTracker wiki)

AI-агент на **Deep Agents** + **LangChain StructuredTools**: загружает **задачу (юнит)** по коду через [`GET /rest/api/unit/v2/{code}`](get_task_definition.txt) (не wiki-плагин), декомпозирует работу и создаёт **новую wiki-страницу** с таблицей оценок (чел.-дни).

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

Полный перечень и комментарии — в [`.env.example`](.env.example), чтение в коде — [`src/config.py`](src/config.py).

| Группа | Переменные |
|--------|------------|
| **TaskTracker** | `TASKTRACKER_BASE_URL` (обязательно), `TASKTRACKER_TOKEN` и/или `TASKTRACKER_BASIC_AUTH` (`user:password`). `TASKTRACKER_VERIFY_SSL` — по умолчанию `false` (не проверять сертификат; поставьте `true`, если нужна строгая проверка TLS). |
| **Режим без записи** | `TASKTRACKER_DRY_RUN=true` — не выполняются реальные POST/PATCH к API (создание wiki, обновление тела, [иерархия](get_wiki_hierarchy.txt), [связь parent/child](link_parent_child.txt) — заглушки). |
| **Модель** | `LLM_MODEL` (по умолчанию `GigaChat-2`). Для GigaChat: `GIGACHAT_API_KEY`, `GIGACHAT_VERIFY_SSL`. Для других моделей — HUB: `HUB_BASE_URL`, `HUB_API_KEY`, `HUB_VERIFY_SSL`. |
| **Wiki** | `WIKI_SPACE` (по умолчанию `VIEW`) — пространство по умолчанию для инструмента `get_wiki_hierarchy`, если не передан список `spaces`. |
| **Прогоны** | `TASK_ESTIMATION_RUNS_DIR` (по умолчанию `runs`) — каталог с `plan.md`, `created_wiki.json`, при `--parent-page` — `parent_link.json`. |
| **LangGraph** (опц.) | `POSTGRES_CHECKPOINT_URL`, `POSTGRES_STORE_URL` — персистентность чата и `/memories/`. |

Родительская wiki-страница для иерархии **не** задаётся через `.env`, только флаг **`--parent-page`** у `single-run` (см. ниже).

## Запуск

Интерактивно:

```bash
uv run python -m src.main --interactive
```

Один прогон по **коду задачи** (юнит, например `VIEW-8168`):

```bash
uv run python -m src.main single-run --task-code VIEW-8168
```

Устаревший алиас: `--wiki-code` (то же самое).

С родительской wiki-страницей (`--parent-page`): агент после **create_wiki_page_estimation** должен вызвать **link_wiki_parent_child**; если вызова не было, но в ответе create есть `code`, CLI выполнит тот же PATCH (fallback):

```bash
uv run python -m src.main single-run --task-code VIEW-8168 --parent-page VIEW-8278
```

С дополнительным текстом:

```bash
uv run python -m src.main single-run --task-code VIEW-8168 --prompt "Уточни риски интеграции."
```

Артефакты: `runs/<run-id>/plan.md`, `created_wiki.json`; при `--parent-page` при успехе — `parent_link.json`.

Исходная задача читается через **get_task_definition** ([`get_task_definition.txt`](get_task_definition.txt)). После создания оценки в wiki агент может вызвать **get_wiki_page** по коду **созданной** страницы, чтобы проверить сохранённую таблицу.

Также доступны **get_wiki_hierarchy** (дерево страниц, `root=null`), примеры: [`get_wiki_hierarchy.txt`](get_wiki_hierarchy.txt), связь родитель–ребёнок: [`link_parent_child.txt`](link_parent_child.txt). Эталон внешнего вида таблицы — [`QA.rtf`](QA.rtf); пример JSON тела (три колонки, TipTap) — [`example_wiki_page_est_table.txt`](example_wiki_page_est_table.txt); полная сетка этапов задаётся в коде.

## Навык Deep Agents

Каталог `skills/` подключён в `build_agent()` как `/skills/`. Правила оценки и колонок таблицы — в [skills/task-cost-estimation/SKILL.md](skills/task-cost-estimation/SKILL.md).

## Примечание по таблице в wiki

Тело страницы — JSON **TipTap/ProseMirror** (`type: doc`, таблица с `table` / `tableRow` / `tableCell`), строка в поле `wiki_page_body`. Сборка в [`src/wiki/adf.py`](src/wiki/adf.py) по [`QA.rtf`](QA.rtf): **три колонки**, **четыре секции** и **фиксированный набор этапов** в каждой (пустые ячейки — 0 и без декомпозиции). В API в `rows` передаются только заполненные этапы; `komanda` / `komponent` (VIEW). В **dekompozitsiya** у каждой подзадачи должна быть оценка в чел.-днях (сумма = `otsenka`); в wiki — `orderedList`, если текст не пустой. Ошибки **SSL/TLS** — от **TaskTracker** (`TASKTRACKER_VERIFY_SSL`) или **LLM Hub** / **GigaChat**.
