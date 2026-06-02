#!/usr/bin/env python3
import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from opentele.api import API
from opentele.tl import TelegramClient
from telethon import utils
from telethon.tl.types import Channel, Chat, User


def session_base(path: str) -> str:
    return path[:-8] if path.endswith(".session") else path


def entity_title(entity: Any) -> str:
    if isinstance(entity, User):
        return " ".join(part for part in [entity.first_name, entity.last_name] if part) or "(unnamed)"
    return getattr(entity, "title", None) or "(untitled)"


def entity_type(entity: Any) -> str:
    if isinstance(entity, User):
        return "bot" if entity.bot else "user"
    if isinstance(entity, Channel):
        if entity.broadcast:
            return "channel"
        if entity.megagroup:
            return "supergroup"
        return "channel"
    if isinstance(entity, Chat):
        return "group"
    return type(entity).__name__


async def open_client(session: str) -> TelegramClient:
    client = TelegramClient(
        session_base(session),
        api=API.TelegramDesktop,
        receive_updates=False,
    )
    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        raise RuntimeError("session is not authorized")
    return client


async def chats_list(args: argparse.Namespace) -> list[dict[str, Any]]:
    client = await open_client(args.session)
    try:
        result = []
        async for dialog in client.iter_dialogs(limit=args.limit):
            entity = dialog.entity
            result.append({
                "peer_id": utils.get_peer_id(entity),
                "id": getattr(entity, "id", None),
                "type": entity_type(entity),
                "title": entity_title(entity),
                "username": getattr(entity, "username", None),
                "unread_count": dialog.unread_count,
            })
        return result
    finally:
        await client.disconnect()


def parse_chat(value: str) -> str | int:
    return int(value) if value.lstrip("-").isdigit() else value


async def messages_recent(args: argparse.Namespace) -> list[dict[str, Any]]:
    client = await open_client(args.session)
    try:
        entity = await client.get_entity(parse_chat(args.chat))
        result = []
        async for message in client.iter_messages(entity, limit=args.limit):
            result.append({
                "id": message.id,
                "date": message.date.isoformat() if message.date else None,
                "sender_id": message.sender_id,
                "text": message.message or "",
                "out": bool(message.out),
                "post": bool(message.post),
                "reply_to_msg_id": message.reply_to_msg_id,
            })
        return result
    finally:
        await client.disconnect()


async def run(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.command == "chats-list":
        return await chats_list(args)
    if args.command == "messages-recent":
        return await messages_recent(args)
    raise RuntimeError(f"unknown command: {args.command}")


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    chats = subparsers.add_parser("chats-list")
    chats.add_argument("--session", required=True)
    chats.add_argument("--limit", type=int, default=30)

    messages = subparsers.add_parser("messages-recent")
    messages.add_argument("--session", required=True)
    messages.add_argument("--chat", required=True)
    messages.add_argument("--limit", type=int, default=20)

    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args)), ensure_ascii=False))


if __name__ == "__main__":
    main()

