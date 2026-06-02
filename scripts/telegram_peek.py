#!/usr/bin/env python3
import argparse
import asyncio
import json
from pathlib import Path
import re
from typing import Any

from opentele.api import API
from opentele.tl import TelegramClient
from telethon import utils
from telethon.tl.types import (
    Channel,
    Chat,
    MessageMediaContact,
    MessageMediaDocument,
    MessageMediaGeo,
    MessageMediaPhoto,
    MessageMediaPoll,
    MessageMediaVenue,
    User,
)


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


def media_kind(message: Any) -> str:
    media = message.media
    if isinstance(media, MessageMediaPhoto):
        return "photo"
    if isinstance(media, MessageMediaDocument):
        file = message.file
        if file:
            if file.mime_type == "application/pdf":
                return "pdf"
            if file.mime_type and file.mime_type.startswith("image/"):
                return "image"
            if file.mime_type and file.mime_type.startswith("video/"):
                return "video"
            if file.mime_type and file.mime_type.startswith("audio/"):
                return "audio"
        return "document"
    if isinstance(media, MessageMediaContact):
        return "contact"
    if isinstance(media, MessageMediaGeo):
        return "location"
    if isinstance(media, MessageMediaVenue):
        return "venue"
    if isinstance(media, MessageMediaPoll):
        return "poll"
    return type(media).__name__ if media else "unknown"


def message_attachments(message: Any, args: argparse.Namespace) -> list[dict[str, Any]]:
    if not message.media:
        return []

    file = message.file
    if not file:
        return [{
            "index": 0,
            "kind": media_kind(message),
            "name": None,
            "mime_type": None,
            "size": None,
            "ext": None,
            "file_id": None,
            "width": None,
            "height": None,
            "duration": None,
            "path": None,
            "downloaded": False,
            "download_skipped": "no_file",
            "download_error": None,
            "path_source": None,
        }]

    existing = find_existing_file(file, args.local_files_dir)
    return [{
        "index": 0,
        "kind": media_kind(message),
        "name": file.name,
        "mime_type": file.mime_type,
        "size": file.size,
        "ext": file.ext,
        "file_id": safe_file_id(file),
        "width": file.width,
        "height": file.height,
        "duration": file.duration,
        "path": str(existing) if existing else None,
        "downloaded": False,
        "download_skipped": None,
        "download_error": None,
        "path_source": args.local_files_dir_source if existing else None,
    }]


def safe_file_id(file: Any) -> str | None:
    try:
        return file.id
    except Exception:
        return None


def find_existing_file(file: Any, roots: list[str]) -> Path | None:
    if not file.name:
        return None

    name = safe_filename(file.name, file.name)
    for root_value in roots:
        root = Path(root_value).expanduser().resolve()
        if not root.exists():
            continue

        direct = root / name
        if is_same_file(direct, file.size):
            return direct

        for candidate in root.rglob(name):
            if is_same_file(candidate, file.size):
                return candidate
    return None


def is_same_file(path: Path, size: int | None) -> bool:
    try:
        if not path.is_file():
            return False
        return size is None or path.stat().st_size == size
    except OSError:
        return False


def safe_filename(value: str | None, fallback: str) -> str:
    name = value or fallback
    name = re.sub(r"[/\\\x00-\x1f]+", "_", name)
    name = name.strip(". ")
    return name or fallback


async def maybe_download_attachments(
    message: Any,
    attachments: list[dict[str, Any]],
    args: argparse.Namespace,
) -> None:
    if not args.download_attachments or not attachments:
        return

    file = message.file
    if not file:
        return

    attachment = attachments[0]
    size = file.size
    max_bytes = args.max_attachment_mb * 1024 * 1024
    if size and size > max_bytes:
        attachment["download_skipped"] = f"size>{args.max_attachment_mb}MiB"
        return

    name = safe_filename(
        file.name,
        f"{message.id}-{attachment['kind']}{file.ext or ''}",
    )
    directory = Path(args.download_dir).resolve() / safe_filename(str(args.chat), "chat") / str(message.id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name

    try:
        downloaded = await message.download_media(file=str(path))
    except Exception as error:
        attachment["download_error"] = str(error)
        return

    if downloaded:
        attachment["path"] = str(Path(downloaded).resolve())
        attachment["downloaded"] = True
        attachment["download_skipped"] = None
        attachment["path_source"] = "downloaded"


async def messages_recent(args: argparse.Namespace) -> list[dict[str, Any]]:
    client = await open_client(args.session)
    try:
        entity = await client.get_entity(parse_chat(args.chat))
        result = []
        async for message in client.iter_messages(entity, limit=args.limit):
            attachments = message_attachments(message, args)
            await maybe_download_attachments(message, attachments, args)
            result.append({
                "id": message.id,
                "date": message.date.isoformat() if message.date else None,
                "sender_id": message.sender_id,
                "text": message.message or "",
                "out": bool(message.out),
                "post": bool(message.post),
                "reply_to_msg_id": message.reply_to_msg_id,
                "attachments": attachments,
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
    messages.add_argument("--download-attachments", action="store_true")
    messages.add_argument("--download-dir", default="data/files")
    messages.add_argument("--max-attachment-mb", type=int, default=25)
    messages.add_argument(
        "--local-files-dir",
        action="append",
        default=[],
    )
    messages.add_argument("--local-files-dir-source")

    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args)), ensure_ascii=False))


if __name__ == "__main__":
    main()
