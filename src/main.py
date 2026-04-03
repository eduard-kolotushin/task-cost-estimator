"""CLI: интерактивный режим и single-run."""
from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from typing import Any, Dict

from dotenv import load_dotenv
from langgraph.types import Command

from src.agent.graph import build_agent, run_once, run_until_done
from src.config import get_runs_dir
from src.run_artifacts import (
    create_run_dir,
    extract_child_code_from_wiki_ops,
    extract_plan_from_result,
    extract_wiki_tool_calls_from_result,
    write_created_wiki,
    write_failure_reason,
    write_parent_link,
    write_plan,
)
from src.wiki.client import WikiClient
from src.wiki.task_unit import format_task_unit_for_prompt

logging.basicConfig(level=logging.INFO)


def _message_content(msg: Any) -> Any:
    if isinstance(msg, dict):
        return msg.get("content")
    return getattr(msg, "content", None)


def _serializable_result(result: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in result.items():
        if key == "messages" and isinstance(value, list):
            out[key] = [
                {"type": type(m).__name__, "content": _message_content(m)}
                for m in value
            ]
        elif isinstance(value, (dict, list, str, int, float, bool, type(None))):
            out[key] = value
        else:
            out[key] = str(value)
    return out


def _pretty_print_result(result: Dict[str, Any]) -> None:
    messages = result.get("messages")
    if isinstance(messages, list) and messages:
        last = messages[-1]
        content = _message_content(last)
        if content:
            print(content)
            return
    print(json.dumps(_serializable_result(result), ensure_ascii=False, indent=2))


def _build_user_message_from_task_code(task_code: str) -> str:
    """Текст запроса из GET /rest/api/unit/v2/{code} (см. get_task_definition.txt)."""
    client = WikiClient.from_env()
    unit = client.get_task_unit(task_code)
    ctx = format_task_unit_for_prompt(unit)
    return f"Задача для оценки ({task_code}):\n\n{ctx}".strip()


def _single_run_main(args: argparse.Namespace) -> int:
    load_dotenv()

    if not args.task_code and not args.prompt:
        print("Ошибка: укажите --task-code и/или --prompt.", file=sys.stderr)
        return 1

    output_dir = args.output_dir or get_runs_dir()
    run_id = args.run_id or str(uuid.uuid4())
    run_dir = create_run_dir(output_dir, run_id)

    failed = False
    failure_parts: list[str] = []
    result: Dict[str, Any] = {}

    try:
        if args.task_code and args.prompt:
            task_msg = _build_user_message_from_task_code(args.task_code)
            user_message = f"{task_msg}\n\nДополнительно: {args.prompt}"
        elif args.task_code:
            user_message = _build_user_message_from_task_code(args.task_code)
        else:
            user_message = args.prompt or ""

        if getattr(args, "parent_page", None):
            user_message = (
                user_message
                + f"\n\n[Система] После создания страницы с оценкой она будет привязана "
                f"к родительской wiki-странице `{args.parent_page}` (связь выполнит среда запуска)."
            )

        agent = build_agent()
        payload = {"messages": [{"role": "user", "content": user_message}]}
        config = {"configurable": {"thread_id": run_id}}
        result = run_until_done(agent, payload, config, auto_approve=True)
    except Exception as e:
        failed = True
        failure_parts.append(f"Исключение: {e}")
        import traceback

        failure_parts.append(traceback.format_exc())

    plan_content = extract_plan_from_result(result)
    if plan_content:
        write_plan(run_dir, plan_content)
    elif failed:
        write_plan(run_dir, "Запуск не удался. См. failure_reason.txt.")

    wiki_ops = extract_wiki_tool_calls_from_result(result)
    write_created_wiki(run_dir, wiki_ops)

    parent_page = getattr(args, "parent_page", None)
    if not failed and parent_page:
        child_code = extract_child_code_from_wiki_ops(wiki_ops)
        if child_code:
            try:
                client = WikiClient.from_env()
                link_res = client.link_wiki_parent_child(
                    parent=parent_page,
                    child=child_code,
                )
                write_parent_link(
                    run_dir,
                    {
                        "parent": parent_page,
                        "child": child_code,
                        "result": link_res,
                    },
                )
                print(
                    f"Связь родитель–потомок: {parent_page} → {child_code}",
                    file=sys.stderr,
                )
            except Exception as e:
                print(f"Не удалось связать с родителем {parent_page}: {e}", file=sys.stderr)
                write_parent_link(
                    run_dir,
                    {
                        "parent": parent_page,
                        "child": child_code,
                        "error": str(e),
                    },
                )
        else:
            print(
                "Параметр --parent-page задан, но код созданной страницы не найден в результатах.",
                file=sys.stderr,
            )
            write_parent_link(
                run_dir,
                {
                    "parent": parent_page,
                    "child": None,
                    "error": "child_code_not_found",
                },
            )

    if failed:
        write_failure_reason(run_dir, "\n\n".join(failure_parts))
        print(f"Ошибка. Артефакты: {run_dir}", file=sys.stderr)
        return 1

    print(f"Готово. Артефакты: {run_dir}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Агент оценки задач TaskTracker wiki (Deep Agents).",
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        help="Текст запроса (если не single-run).",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Интерактивный REPL.",
    )
    parser.add_argument(
        "--thread-id",
        help="Идентификатор потока для истории.",
    )

    sub = parser.add_subparsers(dest="command", help="Команды")
    single = sub.add_parser(
        "single-run",
        help="Один прогон: код задачи (--task-code) или промпт, артефакты в каталог.",
    )
    single.add_argument(
        "--task-code",
        "--wiki-code",
        dest="task_code",
        metavar="CODE",
        help="Код задачи (юнит) TaskTracker, например VIEW-8168. GET /rest/api/unit/v2/{code}. Алиас: --wiki-code.",
    )
    single.add_argument("--prompt", help="Текст требований (или дополнение к --task-code)")
    single.add_argument(
        "--parent-page",
        metavar="CODE",
        default=None,
        help=(
            "Код родительской wiki-страницы: после создания страницы с оценкой "
            "вызвать API связи (child = созданная страница). Без параметра связь не выполняется."
        ),
    )
    single.add_argument("--output-dir", default=None, help="Каталог для артефактов")
    single.add_argument("--run-id", default=None, help="Явный id прогона")

    args = parser.parse_args()

    if args.command == "single-run":
        sys.exit(_single_run_main(args))

    load_dotenv()
    agent = build_agent()

    if args.interactive:
        thread_id = args.thread_id or str(uuid.uuid4())
        print(f"Агент оценки задач. thread_id={thread_id}. Ctrl+C — выход.")
        config = {"configurable": {"thread_id": thread_id}}
        try:
            while True:
                line = input("> ").strip()
                if not line:
                    continue
                result = agent.invoke(
                    {"messages": [{"role": "user", "content": line}]},
                    config=config,
                )
                while result.get("__interrupt__"):
                    interrupts = result["__interrupt__"][0].value
                    action_requests = interrupts["action_requests"]
                    review_configs = interrupts["review_configs"]
                    config_map = {cfg["action_name"]: cfg for cfg in review_configs}
                    decisions = []
                    for idx, action in enumerate(action_requests, start=1):
                        review_config = config_map.get(action["name"], {})
                        allowed = review_config.get(
                            "allowed_decisions", ["approve", "edit", "reject"]
                        )
                        print(
                            f"\nОжидает вызов #{idx}: {action['name']}\n"
                            f"  args: {json.dumps(action['args'], ensure_ascii=False)}\n"
                            f"  решения: {allowed}\n"
                        )
                        while True:
                            choice = (
                                input(f"Решение для {action['name']} ({', '.join(allowed)}): ")
                                .strip()
                                .lower()
                            )
                            if choice not in allowed:
                                print("Неверный ввод.")
                                continue
                            if choice == "edit":
                                print("Введите JSON аргументов или Enter для без изменений.")
                                edited = input("JSON: ").strip()
                                if not edited:
                                    decisions.append({"type": "approve"})
                                else:
                                    try:
                                        edited_args = json.loads(edited)
                                        decisions.append({
                                            "type": "edit",
                                            "edited_action": {
                                                "name": action["name"],
                                                "args": edited_args,
                                            },
                                        })
                                    except json.JSONDecodeError as e:
                                        print(f"Неверный JSON: {e}")
                                        continue
                            else:
                                decisions.append({"type": choice})
                            break
                    result = agent.invoke(
                        Command(resume={"decisions": decisions}),
                        config=config,
                    )
                _pretty_print_result(result)
        except KeyboardInterrupt:
            print("\nВыход.")
    else:
        if not args.prompt:
            parser.error("Укажите PROMPT или --interactive.")
        result = run_once(agent, args.prompt, thread_id=args.thread_id)
        _pretty_print_result(result)


if __name__ == "__main__":
    main()
