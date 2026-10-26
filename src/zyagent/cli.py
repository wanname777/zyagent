from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional, Sequence

from zyagent.application.service import SessionNotFoundError
from zyagent.domain.messages import AssistantMessage, ToolResult, UserMessage
from zyagent.main import AppConfig, build_service


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        prog="zyagent",
        description="A clean-architecture agent with branching and context compression.",
    )
    command.add_argument(
        "--data-path",
        type=Path,
        default=Path(
            os.getenv("ZYAGENT_DATA", "~/.zyagent/sessions.jsonl")
        ).expanduser(),
    )
    command.add_argument("--workspace", type=Path, default=Path.cwd())
    command.add_argument(
        "--base-url",
        default=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    )
    command.add_argument(
        "--model",
        default=os.getenv("ZYAGENT_MODEL", "gpt-4.1-mini"),
    )
    command.add_argument(
        "--reviewer-model",
        default=os.getenv("ZYAGENT_REVIEWER_MODEL", "gpt-4.1-mini"),
    )
    command.add_argument(
        "--compression-model",
        default=os.getenv("ZYAGENT_COMPRESSION_MODEL", "gpt-4.1-mini"),
    )

    subcommands = command.add_subparsers(dest="command", required=True)
    chat = subcommands.add_parser("chat", help="Start or continue a conversation.")
    chat.add_argument("--session", help="Existing session ID.")
    chat.add_argument("prompt", nargs="*", help="Optional one-shot prompt.")

    subcommands.add_parser("list", help="List stored conversations.")

    show = subcommands.add_parser("show", help="Show one conversation.")
    show.add_argument("session")

    branch = subcommands.add_parser("branch", help="Branch at a historical message.")
    branch.add_argument("session")
    branch.add_argument("message")
    branch.add_argument("--new-id")

    compress = subcommands.add_parser(
        "compress", help="Summarize old context while preserving full history."
    )
    compress.add_argument("session")
    compress.add_argument("--keep-recent", type=int, default=12)
    return command


def config_from_args(args: argparse.Namespace) -> AppConfig:
    return AppConfig(
        api_key=os.getenv("OPENAI_API_KEY", ""),
        base_url=args.base_url,
        data_path=args.data_path.expanduser().resolve(),
        workspace=args.workspace.expanduser().resolve(),
        assistant_model=args.model,
        reviewer_model=args.reviewer_model,
        compression_model=args.compression_model,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    service = build_service(config_from_args(args))
    try:
        if args.command == "list":
            for session in service.list_sessions():
                print(
                    f"{session.id}\t{len(session.messages)} messages"
                    f"\tupdated {session.updated_at}"
                )
            return 0
        if args.command == "show":
            session = service.get_session(args.session)
            _print_session(session)
            return 0
        if args.command == "branch":
            session = service.branch_session(
                args.session,
                args.message,
                args.new_id,
            )
            print(session.id)
            return 0
        if args.command == "compress":
            session = service.compress_session(
                args.session,
                keep_recent=args.keep_recent,
            )
            print(
                f"{session.id}: {len(session.context_messages())} active messages, "
                f"{len(session.messages)} total messages"
            )
            return 0
        if args.command == "chat":
            return _chat(service, args.session, " ".join(args.prompt).strip())
    except (SessionNotFoundError, ValueError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 2


def _chat(service: object, session_id: Optional[str], prompt: str) -> int:
    if session_id:
        session = service.get_session(session_id)
    else:
        session = service.create_session()
    print(f"session: {session.id}")

    if prompt:
        response = service.send_message(session.id, prompt)
        print(response.text)
        return 0

    print("Type /exit to stop.")
    while True:
        try:
            text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not text:
            continue
        if text in {"/exit", "/quit"}:
            return 0
        response = service.send_message(session.id, text)
        print(f"zyagent> {response.text}")


def _print_session(session: object) -> None:
    print(f"session: {session.id}")
    if session.parent_session_id:
        print(
            f"branched from: {session.parent_session_id} at {session.branch_message_id}"
        )
    if session.summary:
        print(f"summary through {session.summary_through_message_id}:")
        print(session.summary)
    for message in session.messages:
        if isinstance(message, UserMessage):
            label = "user"
            body = message.text
        elif isinstance(message, AssistantMessage):
            label = "assistant"
            calls = ", ".join(call.name for call in message.tool_calls)
            body = message.text
            if calls:
                body = f"{body}\n  tool calls: {calls}".strip()
        elif isinstance(message, ToolResult):
            label = "tool-error" if message.is_error else "tool"
            body = message.content
        else:
            continue
        print(f"[{message.id}] {label}: {body}")


if __name__ == "__main__":
    raise SystemExit(main())
