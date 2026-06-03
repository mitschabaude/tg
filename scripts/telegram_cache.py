#!/usr/bin/env python3
import argparse
import asyncio
import json
import sqlite3
from pathlib import Path
import re
import sys
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
    PeerChannel,
    PeerChat,
    PeerUser,
    ReactionCustomEmoji,
    ReactionEmoji,
    ReactionEmpty,
    ReactionPaid,
    User,
)


def session_base(path: str) -> str:
    return path[:-8] if path.endswith(".session") else path


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


def connect(db_path: str) -> sqlite3.Connection:
    return connect_write(db_path)


def connect_write(db_path: str) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    db = sqlite3.connect(path)
    path.chmod(0o600)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    ensure_schema(db)
    migrate_schema(db)
    return db


def connect_read(db_path: str) -> sqlite3.Connection:
    path = Path(db_path)
    if not path.exists():
        raise RuntimeError("cache is empty; run: npm run tg -- sync chats")
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def ensure_schema(db: sqlite3.Connection) -> None:
    db.executescript("""
        CREATE TABLE IF NOT EXISTS chats (
            peer_id INTEGER PRIMARY KEY,
            id INTEGER,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            username TEXT,
            unread_count INTEGER NOT NULL DEFAULT 0,
            last_message_id INTEGER,
            last_message_date TEXT,
            dialog_order INTEGER,
            synced_at TEXT NOT NULL,
            normalized_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS peers (
            peer_id INTEGER PRIMARY KEY,
            id INTEGER,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            username TEXT,
            synced_at TEXT NOT NULL,
            normalized_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS messages (
            chat_peer_id INTEGER NOT NULL,
            id INTEGER NOT NULL,
            date TEXT,
            edit_date TEXT,
            sender_id INTEGER,
            text TEXT NOT NULL,
            out INTEGER NOT NULL,
            post INTEGER NOT NULL,
            reply_to_msg_id INTEGER,
            fetched_at TEXT NOT NULL,
            normalized_json TEXT NOT NULL,
            PRIMARY KEY (chat_peer_id, id)
        );

        CREATE TABLE IF NOT EXISTS attachments (
            chat_peer_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            idx INTEGER NOT NULL,
            kind TEXT NOT NULL,
            name TEXT,
            mime_type TEXT,
            size INTEGER,
            ext TEXT,
            file_id TEXT,
            width INTEGER,
            height INTEGER,
            duration REAL,
            path TEXT,
            downloaded INTEGER NOT NULL,
            download_skipped TEXT,
            download_error TEXT,
            path_source TEXT,
            normalized_json TEXT NOT NULL,
            PRIMARY KEY (chat_peer_id, message_id, idx),
            FOREIGN KEY (chat_peer_id, message_id)
                REFERENCES messages(chat_peer_id, id)
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS message_reaction_counts (
            chat_peer_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            idx INTEGER NOT NULL,
            kind TEXT NOT NULL,
            emoticon TEXT,
            custom_emoji_document_id TEXT,
            count INTEGER NOT NULL,
            chosen_order INTEGER,
            normalized_json TEXT NOT NULL,
            PRIMARY KEY (chat_peer_id, message_id, idx),
            FOREIGN KEY (chat_peer_id, message_id)
                REFERENCES messages(chat_peer_id, id)
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS message_recent_reactions (
            chat_peer_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            idx INTEGER NOT NULL,
            reactor_peer_id INTEGER,
            reaction_kind TEXT NOT NULL,
            emoticon TEXT,
            custom_emoji_document_id TEXT,
            date TEXT,
            big INTEGER NOT NULL,
            unread INTEGER NOT NULL,
            my INTEGER NOT NULL,
            normalized_json TEXT NOT NULL,
            PRIMARY KEY (chat_peer_id, message_id, idx),
            FOREIGN KEY (chat_peer_id, message_id)
                REFERENCES messages(chat_peer_id, id)
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS sync_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS chats_dialog_order_idx
            ON chats(dialog_order);
        CREATE INDEX IF NOT EXISTS chats_last_message_idx
            ON chats(last_message_date DESC, last_message_id DESC);
        CREATE INDEX IF NOT EXISTS messages_chat_date_idx
            ON messages(chat_peer_id, date DESC, id DESC);
        CREATE INDEX IF NOT EXISTS chats_username_idx
            ON chats(username);
        CREATE INDEX IF NOT EXISTS peers_username_idx
            ON peers(username);
        CREATE INDEX IF NOT EXISTS message_recent_reactions_reactor_idx
            ON message_recent_reactions(reactor_peer_id);
    """)


def migrate_schema(db: sqlite3.Connection) -> None:
    rename_column_if_exists(db, "chats", "raw_json", "normalized_json")
    rename_column_if_exists(db, "messages", "raw_json", "normalized_json")
    rename_column_if_exists(db, "attachments", "raw_json", "normalized_json")


def rename_column_if_exists(db: sqlite3.Connection, table: str, old: str, new: str) -> None:
    columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
    if old in columns and new not in columns:
        db.execute(f"ALTER TABLE {table} RENAME COLUMN {old} TO {new}")


def now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def parse_chat(value: str) -> str | int:
    return int(value) if value.lstrip("-").isdigit() else value


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


def entity_row(entity: Any, synced_at: str) -> dict[str, Any]:
    return {
        "peer_id": utils.get_peer_id(entity),
        "id": getattr(entity, "id", None),
        "type": entity_type(entity),
        "title": entity_title(entity),
        "username": getattr(entity, "username", None),
        "synced_at": synced_at,
    }


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


def message_attachments(message: Any, local_files_dir: list[str], path_source: str | None) -> list[dict[str, Any]]:
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

    existing = find_existing_file(file, local_files_dir)
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
        "path_source": path_source if existing else None,
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


def reaction_value(reaction: Any) -> dict[str, Any]:
    if isinstance(reaction, ReactionEmoji):
        return {
            "kind": "emoji",
            "emoticon": reaction.emoticon,
            "custom_emoji_document_id": None,
        }
    if isinstance(reaction, ReactionCustomEmoji):
        return {
            "kind": "custom_emoji",
            "emoticon": None,
            "custom_emoji_document_id": str(reaction.document_id),
        }
    if isinstance(reaction, ReactionPaid):
        return {
            "kind": "paid",
            "emoticon": None,
            "custom_emoji_document_id": None,
        }
    if isinstance(reaction, ReactionEmpty):
        return {
            "kind": "empty",
            "emoticon": None,
            "custom_emoji_document_id": None,
        }
    return {
        "kind": type(reaction).__name__ if reaction else "unknown",
        "emoticon": None,
        "custom_emoji_document_id": None,
    }


def reaction_key(row: dict[str, Any]) -> tuple[str, str | None, str | None]:
    return (row["kind"], row["emoticon"], row["custom_emoji_document_id"])


def peer_id_value(peer: Any) -> int | None:
    if isinstance(peer, PeerUser):
        return peer.user_id
    if isinstance(peer, PeerChat):
        return -peer.chat_id
    if isinstance(peer, PeerChannel):
        return utils.get_peer_id(peer)
    return None


def message_reactions(message: Any) -> dict[str, Any]:
    reactions = message.reactions
    if not reactions:
        return {
            "counts": [],
            "recent": [],
            "recent_complete": False,
        }

    counts = []
    for index, item in enumerate(reactions.results or []):
        value = reaction_value(item.reaction)
        counts.append({
            "index": index,
            **value,
            "count": item.count,
            "chosen_order": item.chosen_order,
        })

    recent = []
    for index, item in enumerate(reactions.recent_reactions or []):
        value = reaction_value(item.reaction)
        recent.append({
            "index": index,
            "reactor_peer_id": peer_id_value(item.peer_id),
            **value,
            "date": item.date.isoformat() if item.date else None,
            "big": bool(item.big),
            "unread": bool(item.unread),
            "my": bool(item.my),
        })

    remaining = {reaction_key(count): count["count"] for count in counts}
    for item in recent:
        key = reaction_key(item)
        if key in remaining:
            remaining[key] -= 1
    return {
        "counts": counts,
        "recent": recent,
        "recent_complete": bool(counts) and all(count == 0 for count in remaining.values()),
    }


def chat_row(entity: Any, dialog: Any | None, order: int | None, synced_at: str) -> dict[str, Any]:
    message = getattr(dialog, "message", None) if dialog else None
    return {
        "peer_id": utils.get_peer_id(entity),
        "id": getattr(entity, "id", None),
        "type": entity_type(entity),
        "title": entity_title(entity),
        "username": getattr(entity, "username", None),
        "unread_count": getattr(dialog, "unread_count", 0) if dialog else 0,
        "last_message_id": getattr(message, "id", None),
        "last_message_date": message.date.isoformat() if message and message.date else None,
        "dialog_order": order,
        "synced_at": synced_at,
    }


def upsert_chat(db: sqlite3.Connection, row: dict[str, Any]) -> None:
    db.execute("""
        INSERT INTO chats (
            peer_id, id, type, title, username, unread_count,
            last_message_id, last_message_date, dialog_order, synced_at, normalized_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(peer_id) DO UPDATE SET
            id = excluded.id,
            type = excluded.type,
            title = excluded.title,
            username = excluded.username,
            unread_count = CASE
                WHEN excluded.dialog_order IS NULL THEN chats.unread_count
                ELSE excluded.unread_count
            END,
            last_message_id = COALESCE(excluded.last_message_id, chats.last_message_id),
            last_message_date = COALESCE(excluded.last_message_date, chats.last_message_date),
            dialog_order = COALESCE(excluded.dialog_order, chats.dialog_order),
            synced_at = excluded.synced_at,
            normalized_json = excluded.normalized_json
    """, (
        row["peer_id"],
        row["id"],
        row["type"],
        row["title"],
        row["username"],
        row["unread_count"],
        row["last_message_id"],
        row["last_message_date"],
        row["dialog_order"],
        row["synced_at"],
        json.dumps(row, ensure_ascii=False),
    ))
    upsert_peer(db, {
        "peer_id": row["peer_id"],
        "id": row["id"],
        "type": row["type"],
        "title": row["title"],
        "username": row["username"],
        "synced_at": row["synced_at"],
    })


def upsert_peer(db: sqlite3.Connection, row: dict[str, Any]) -> None:
    db.execute("""
        INSERT INTO peers (
            peer_id, id, type, title, username, synced_at, normalized_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(peer_id) DO UPDATE SET
            id = excluded.id,
            type = excluded.type,
            title = excluded.title,
            username = excluded.username,
            synced_at = excluded.synced_at,
            normalized_json = excluded.normalized_json
    """, (
        row["peer_id"],
        row["id"],
        row["type"],
        row["title"],
        row["username"],
        row["synced_at"],
        json.dumps(row, ensure_ascii=False),
    ))


def message_row(
    chat_peer_id: int,
    message: Any,
    attachments: list[dict[str, Any]],
    reactions: dict[str, Any],
    fetched_at: str,
) -> dict[str, Any]:
    return {
        "chat_peer_id": chat_peer_id,
        "id": message.id,
        "date": message.date.isoformat() if message.date else None,
        "edit_date": message.edit_date.isoformat() if getattr(message, "edit_date", None) else None,
        "sender_id": message.sender_id,
        "text": message.message or "",
        "out": bool(message.out),
        "post": bool(message.post),
        "reply_to_msg_id": message.reply_to_msg_id,
        "attachments": attachments,
        "reaction_counts": reactions["counts"],
        "recent_reactions": reactions["recent"],
        "reactions_complete": reactions["recent_complete"],
        "fetched_at": fetched_at,
    }


def upsert_message(db: sqlite3.Connection, row: dict[str, Any]) -> None:
    db.execute("""
        INSERT INTO messages (
            chat_peer_id, id, date, edit_date, sender_id, text, out, post,
            reply_to_msg_id, fetched_at, normalized_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(chat_peer_id, id) DO UPDATE SET
            date = excluded.date,
            edit_date = excluded.edit_date,
            sender_id = excluded.sender_id,
            text = excluded.text,
            out = excluded.out,
            post = excluded.post,
            reply_to_msg_id = excluded.reply_to_msg_id,
            fetched_at = excluded.fetched_at,
            normalized_json = excluded.normalized_json
    """, (
        row["chat_peer_id"],
        row["id"],
        row["date"],
        row["edit_date"],
        row["sender_id"],
        row["text"],
        int(row["out"]),
        int(row["post"]),
        row["reply_to_msg_id"],
        row["fetched_at"],
        json.dumps(row, ensure_ascii=False),
    ))
    db.execute(
        "DELETE FROM attachments WHERE chat_peer_id = ? AND message_id = ?",
        (row["chat_peer_id"], row["id"]),
    )
    for attachment in row["attachments"]:
        db.execute("""
            INSERT INTO attachments (
                chat_peer_id, message_id, idx, kind, name, mime_type, size,
                ext, file_id, width, height, duration, path, downloaded,
                download_skipped, download_error, path_source, normalized_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            row["chat_peer_id"],
            row["id"],
            attachment["index"],
            attachment["kind"],
            attachment["name"],
            attachment["mime_type"],
            attachment["size"],
            attachment["ext"],
            attachment["file_id"],
            attachment["width"],
            attachment["height"],
            attachment["duration"],
            attachment["path"],
            int(attachment["downloaded"]),
            attachment["download_skipped"],
            attachment["download_error"],
            attachment["path_source"],
            json.dumps(attachment, ensure_ascii=False),
        ))
    db.execute(
        "DELETE FROM message_reaction_counts WHERE chat_peer_id = ? AND message_id = ?",
        (row["chat_peer_id"], row["id"]),
    )
    for reaction in row["reaction_counts"]:
        db.execute("""
            INSERT INTO message_reaction_counts (
                chat_peer_id, message_id, idx, kind, emoticon,
                custom_emoji_document_id, count, chosen_order, normalized_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            row["chat_peer_id"],
            row["id"],
            reaction["index"],
            reaction["kind"],
            reaction["emoticon"],
            reaction["custom_emoji_document_id"],
            reaction["count"],
            reaction["chosen_order"],
            json.dumps(reaction, ensure_ascii=False),
        ))
    db.execute(
        "DELETE FROM message_recent_reactions WHERE chat_peer_id = ? AND message_id = ?",
        (row["chat_peer_id"], row["id"]),
    )
    for reaction in row["recent_reactions"]:
        db.execute("""
            INSERT INTO message_recent_reactions (
                chat_peer_id, message_id, idx, reactor_peer_id, reaction_kind,
                emoticon, custom_emoji_document_id, date, big, unread, my,
                normalized_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            row["chat_peer_id"],
            row["id"],
            reaction["index"],
            reaction["reactor_peer_id"],
            reaction["kind"],
            reaction["emoticon"],
            reaction["custom_emoji_document_id"],
            reaction["date"],
            int(reaction["big"]),
            int(reaction["unread"]),
            int(reaction["my"]),
            json.dumps(reaction, ensure_ascii=False),
        ))


async def sync_chats(args: argparse.Namespace) -> dict[str, Any]:
    db = connect_write(args.db)
    client = await open_client(args.session)
    synced_at = now_iso()
    count = 0
    try:
        async for dialog in client.iter_dialogs(limit=args.limit):
            upsert_chat(db, chat_row(dialog.entity, dialog, count, synced_at))
            count += 1
        db.execute(
            "INSERT OR REPLACE INTO sync_state(key, value) VALUES (?, ?)",
            ("chats_synced_at", synced_at),
        )
        db.commit()
        return {"synced_chats": count, "synced_at": synced_at}
    finally:
        await client.disconnect()
        db.close()


async def sync_messages(args: argparse.Namespace) -> dict[str, Any]:
    db = connect_write(args.db)
    client = await open_client(args.session)
    fetched_at = now_iso()
    count = 0
    try:
        entity = await client.get_entity(parse_chat(args.chat))
        peer_id = utils.get_peer_id(entity)
        validate_peer_id_argument(args.chat, peer_id)
        upsert_chat(db, chat_row(entity, None, None, fetched_at))
        limit = None if args.full else args.limit
        async for message in client.iter_messages(
            entity,
            limit=limit,
            add_offset=args.offset,
        ):
            attachments = message_attachments(
                message,
                args.local_files_dir,
                args.local_files_dir_source,
            )
            if message.sender:
                upsert_peer(db, entity_row(message.sender, fetched_at))
            upsert_message(db, message_row(
                peer_id,
                message,
                attachments,
                message_reactions(message),
                fetched_at,
            ))
            count += 1
        db.execute(
            "INSERT OR REPLACE INTO sync_state(key, value) VALUES (?, ?)",
            (f"messages_synced_at:{peer_id}", fetched_at),
        )
        db.commit()
        return {
            "chat": peer_id,
            "synced_messages": count,
            "synced_at": fetched_at,
        }
    finally:
        await client.disconnect()
        db.close()


def validate_peer_id_argument(value: str, peer_id: int) -> None:
    if value.lstrip("-").isdigit() and int(value) != peer_id:
        raise RuntimeError(f"chat argument must be canonical peer_id {peer_id}; get peer ids from tg chats list")


def list_chats(args: argparse.Namespace) -> list[dict[str, Any]]:
    db = connect_read(args.db)
    try:
        if scalar(db, "SELECT COUNT(*) FROM chats") == 0:
            raise RuntimeError("cache is empty; run: npm run tg -- sync chats")
        rows = db.execute("""
            SELECT peer_id, id, type, title, username, unread_count
            FROM chats
            ORDER BY
                CASE WHEN dialog_order IS NULL THEN 1 ELSE 0 END,
                dialog_order ASC,
                last_message_date DESC,
                peer_id DESC
            LIMIT ? OFFSET ?
        """, (args.limit, args.offset)).fetchall()
        return [dict(row) for row in rows]
    finally:
        db.close()


def list_messages(args: argparse.Namespace) -> list[dict[str, Any]]:
    db = connect_read(args.db)
    try:
        chat_peer_id = resolve_cached_chat(db, args.chat)
        rows = db.execute("""
            SELECT id, date, sender_id, text, out, post, reply_to_msg_id
            FROM messages
            WHERE chat_peer_id = ?
            ORDER BY date DESC, id DESC
            LIMIT ? OFFSET ?
        """, (chat_peer_id, args.limit, args.offset)).fetchall()
        if not rows and scalar(db, "SELECT COUNT(*) FROM messages WHERE chat_peer_id = ?", (chat_peer_id,)) == 0:
            raise RuntimeError(f"no cached messages for chat {args.chat}; run: npm run tg -- sync messages --chat {args.chat} --limit 1000")
        return [message_from_db(db, chat_peer_id, row) for row in rows]
    finally:
        db.close()


def resolve_cached_chat(db: sqlite3.Connection, value: str) -> int:
    if value.lstrip("-").isdigit():
        peer_id = int(value)
        if db.execute("SELECT 1 FROM chats WHERE peer_id = ?", (peer_id,)).fetchone():
            return peer_id
        if db.execute("SELECT 1 FROM messages WHERE chat_peer_id = ? LIMIT 1", (peer_id,)).fetchone():
            return peer_id
        raise RuntimeError(f"peer id is not cached: {value}; run: npm run tg -- sync chats and use the peer_id from tg chats list")

    username = value[1:] if value.startswith("@") else value
    row = db.execute(
        "SELECT peer_id FROM chats WHERE username = ? COLLATE NOCASE",
        (username,),
    ).fetchone()
    if not row:
        raise RuntimeError(f"chat is not cached: {value}; run: npm run tg -- sync chats")
    return row["peer_id"]


def message_from_db(db: sqlite3.Connection, chat_peer_id: int, row: sqlite3.Row) -> dict[str, Any]:
    sender = peer_from_db(db, row["sender_id"])
    attachments = db.execute("""
        SELECT idx, kind, name, mime_type, size, ext, file_id, width, height,
            duration, path, downloaded, download_skipped, download_error, path_source
        FROM attachments
        WHERE chat_peer_id = ? AND message_id = ?
        ORDER BY idx ASC
    """, (chat_peer_id, row["id"])).fetchall()
    reaction_counts = db.execute("""
        SELECT idx, kind, emoticon, custom_emoji_document_id, count, chosen_order
        FROM message_reaction_counts
        WHERE chat_peer_id = ? AND message_id = ?
        ORDER BY idx ASC
    """, (chat_peer_id, row["id"])).fetchall() if table_exists(db, "message_reaction_counts") else []
    recent_reactions = recent_reactions_from_db(db, chat_peer_id, row["id"])
    reactions_complete = reactions_are_complete(reaction_counts, recent_reactions)
    return {
        "id": row["id"],
        "date": row["date"],
        "sender_id": row["sender_id"],
        "sender_title": sender["title"] if sender else None,
        "sender_username": sender["username"] if sender else None,
        "text": row["text"],
        "out": bool(row["out"]),
        "post": bool(row["post"]),
        "reply_to_msg_id": row["reply_to_msg_id"],
        "attachments": [{
            "index": attachment["idx"],
            "kind": attachment["kind"],
            "name": attachment["name"],
            "mime_type": attachment["mime_type"],
            "size": attachment["size"],
            "ext": attachment["ext"],
            "file_id": attachment["file_id"],
            "width": attachment["width"],
            "height": attachment["height"],
            "duration": attachment["duration"],
            "path": attachment["path"],
            "downloaded": bool(attachment["downloaded"]),
            "download_skipped": attachment["download_skipped"],
            "download_error": attachment["download_error"],
            "path_source": attachment["path_source"],
        } for attachment in attachments],
        "reaction_counts": [{
            "index": reaction["idx"],
            "kind": reaction["kind"],
            "emoticon": reaction["emoticon"],
            "custom_emoji_document_id": string_or_none(reaction["custom_emoji_document_id"]),
            "count": reaction["count"],
            "chosen_order": reaction["chosen_order"],
        } for reaction in reaction_counts],
        "recent_reactions": [{
            "index": reaction["idx"],
            "reactor_peer_id": reaction["reactor_peer_id"],
            "reactor_title": reaction["reactor_title"],
            "reactor_username": reaction["reactor_username"],
            "kind": reaction["reaction_kind"],
            "emoticon": reaction["emoticon"],
            "custom_emoji_document_id": string_or_none(reaction["custom_emoji_document_id"]),
            "date": reaction["date"],
            "big": bool(reaction["big"]),
            "unread": bool(reaction["unread"]),
            "my": bool(reaction["my"]),
        } for reaction in recent_reactions],
        "reactions_complete": reactions_complete,
    }


def peer_from_db(db: sqlite3.Connection, peer_id: int | None) -> sqlite3.Row | None:
    if peer_id is None or not table_exists(db, "peers"):
        return None
    return db.execute(
        "SELECT title, username FROM peers WHERE peer_id = ?",
        (peer_id,),
    ).fetchone()


def recent_reactions_from_db(
    db: sqlite3.Connection,
    chat_peer_id: int,
    message_id: int,
) -> list[sqlite3.Row]:
    if not table_exists(db, "message_recent_reactions"):
        return []
    if table_exists(db, "peers"):
        return db.execute("""
            SELECT r.idx, r.reactor_peer_id, p.title AS reactor_title,
                p.username AS reactor_username, r.reaction_kind, r.emoticon,
                custom_emoji_document_id, date, big, unread, my
            FROM message_recent_reactions r
            LEFT JOIN peers p ON p.peer_id = r.reactor_peer_id
            WHERE r.chat_peer_id = ? AND r.message_id = ?
            ORDER BY r.idx ASC
        """, (chat_peer_id, message_id)).fetchall()
    return db.execute("""
        SELECT idx, reactor_peer_id, NULL AS reactor_title,
            NULL AS reactor_username, reaction_kind, emoticon,
            custom_emoji_document_id, date, big, unread, my
        FROM message_recent_reactions
        WHERE chat_peer_id = ? AND message_id = ?
        ORDER BY idx ASC
    """, (chat_peer_id, message_id)).fetchall()


def reactions_are_complete(
    reaction_counts: list[sqlite3.Row],
    recent_reactions: list[sqlite3.Row],
) -> bool:
    remaining = {
        (row["kind"], row["emoticon"], row["custom_emoji_document_id"]): row["count"]
        for row in reaction_counts
    }
    for row in recent_reactions:
        key = (row["reaction_kind"], row["emoticon"], row["custom_emoji_document_id"])
        if key in remaining:
            remaining[key] -= 1
    return bool(remaining) and all(count == 0 for count in remaining.values())


def string_or_none(value: Any) -> str | None:
    return None if value is None else str(value)


def table_exists(db: sqlite3.Connection, table: str) -> bool:
    return db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone() is not None


def cache_status(args: argparse.Namespace) -> dict[str, Any]:
    if not Path(args.db).exists():
        return {
            "db": args.db,
            "chats": {
                "count": 0,
                "synced_at": None,
            },
            "peers": {
                "count": 0,
            },
            "messages": {
                "count": 0,
                "chats": [],
            },
        }

    db = connect_read(args.db)
    try:
        chat_count = scalar(db, "SELECT COUNT(*) FROM chats")
        peer_count = scalar(db, "SELECT COUNT(*) FROM peers") if table_exists(db, "peers") else 0
        message_count = scalar(db, "SELECT COUNT(*) FROM messages")
        chats_synced_at = state_value(db, "chats_synced_at")
        message_chats = db.execute("""
            SELECT m.chat_peer_id, c.title, COUNT(*) AS count,
                MAX(m.date) AS newest, MIN(m.date) AS oldest,
                MAX(m.fetched_at) AS synced_at
            FROM messages m
            LEFT JOIN chats c ON c.peer_id = m.chat_peer_id
            GROUP BY m.chat_peer_id, c.title
            ORDER BY MAX(m.fetched_at) DESC
            LIMIT 20
        """).fetchall()
        return {
            "db": args.db,
            "chats": {
                "count": chat_count,
                "synced_at": chats_synced_at,
            },
            "peers": {
                "count": peer_count,
            },
            "messages": {
                "count": message_count,
                "chats": [dict(row) for row in message_chats],
            },
        }
    finally:
        db.close()


def scalar(db: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> Any:
    return db.execute(sql, params).fetchone()[0]


def state_value(db: sqlite3.Connection, key: str) -> str | None:
    row = db.execute("SELECT value FROM sync_state WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


async def run(args: argparse.Namespace) -> Any:
    if args.command == "sync-chats":
        return await sync_chats(args)
    if args.command == "sync-messages":
        return await sync_messages(args)
    if args.command == "list-chats":
        return list_chats(args)
    if args.command == "list-messages":
        return list_messages(args)
    if args.command == "cache-status":
        return cache_status(args)
    raise RuntimeError(f"unknown command: {args.command}")


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync_chats_parser = subparsers.add_parser("sync-chats")
    sync_chats_parser.add_argument("--db", required=True)
    sync_chats_parser.add_argument("--session", required=True)
    sync_chats_parser.add_argument("--limit", type=int, default=100)

    sync_messages_parser = subparsers.add_parser("sync-messages")
    sync_messages_parser.add_argument("--db", required=True)
    sync_messages_parser.add_argument("--session", required=True)
    sync_messages_parser.add_argument("--chat", required=True)
    sync_messages_parser.add_argument("--limit", type=int, default=100)
    sync_messages_parser.add_argument("--offset", type=int, default=0)
    sync_messages_parser.add_argument("--full", action="store_true")
    sync_messages_parser.add_argument("--local-files-dir", action="append", default=[])
    sync_messages_parser.add_argument("--local-files-dir-source")

    list_chats_parser = subparsers.add_parser("list-chats")
    list_chats_parser.add_argument("--db", required=True)
    list_chats_parser.add_argument("--limit", type=int, default=30)
    list_chats_parser.add_argument("--offset", type=int, default=0)

    list_messages_parser = subparsers.add_parser("list-messages")
    list_messages_parser.add_argument("--db", required=True)
    list_messages_parser.add_argument("--chat", required=True)
    list_messages_parser.add_argument("--limit", type=int, default=20)
    list_messages_parser.add_argument("--offset", type=int, default=0)

    status_parser = subparsers.add_parser("cache-status")
    status_parser.add_argument("--db", required=True)

    args = parser.parse_args()
    try:
        print(json.dumps(asyncio.run(run(args)), ensure_ascii=False))
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
