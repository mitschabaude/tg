#!/usr/bin/env python3
import argparse
import asyncio
import json
import logging
import sqlite3
import sys
from typing import Any

from opentele.api import API
from opentele.tl import TelegramClient
from telethon import events, utils
from telethon.tl.types import UpdateMessageReactions

from telegram_cache import (
    chat_row,
    connect_write,
    entity_row,
    message_attachments,
    message_from_db,
    message_reactions,
    message_row,
    now_iso,
    session_base,
    upsert_chat,
    upsert_message,
    upsert_peer,
)

INITIAL_MESSAGES = 100


def cached_message(db: sqlite3.Connection, chat_peer_id: int, message_id: int) -> dict[str, Any] | None:
    row = db.execute("""
        SELECT id, date, sender_id, fwd_from_peer_id, fwd_from_name,
            fwd_date, fwd_channel_post, fwd_post_author,
            fwd_saved_from_peer_id, fwd_saved_from_msg_id, text, out,
            post, reply_to_msg_id
        FROM messages
        WHERE chat_peer_id = ? AND id = ?
    """, (chat_peer_id, message_id)).fetchone()
    return message_from_db(db, chat_peer_id, row) if row else None


def reaction_state(message: dict[str, Any] | None) -> str | None:
    if message is None:
        return None
    return json.dumps({
        "counts": message["reaction_counts"],
        "recent": message["recent_reactions"],
    }, ensure_ascii=False, sort_keys=True)


async def cache_one(
    db: sqlite3.Connection,
    chat_peer_id: int,
    message: Any,
    fetched_at: str,
    local_files_dir: list[str],
    local_files_dir_source: str | None,
) -> None:
    sender = await message.get_sender()
    if sender:
        upsert_peer(db, entity_row(sender, fetched_at))
    upsert_message(db, message_row(
        chat_peer_id,
        message,
        message_attachments(message, local_files_dir, local_files_dir_source),
        message_reactions(message),
        fetched_at,
    ))


async def sync_chat(
    db: sqlite3.Connection,
    client: TelegramClient,
    entity: Any,
    trigger: Any,
    local_files_dir: list[str],
    local_files_dir_source: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    chat_peer_id = utils.get_peer_id(entity)
    newest = db.execute(
        "SELECT MAX(id) FROM messages WHERE chat_peer_id = ?",
        (chat_peer_id,),
    ).fetchone()[0]
    fetched_at = now_iso()

    if newest is None:
        messages = [message async for message in client.iter_messages(
            entity,
            limit=INITIAL_MESSAGES,
        )]
    else:
        messages = [message async for message in client.iter_messages(
            entity,
            min_id=newest,
            reverse=True,
        )]

    if not any(message.id == trigger.id for message in messages):
        messages.append(trigger)
    for message in messages:
        await cache_one(
            db,
            chat_peer_id,
            message,
            fetched_at,
            local_files_dir,
            local_files_dir_source,
        )

    latest = db.execute("""
        SELECT id, date FROM messages
        WHERE chat_peer_id = ?
        ORDER BY date DESC, id DESC
        LIMIT 1
    """, (chat_peer_id,)).fetchone()
    chat = chat_row(entity, None, None, fetched_at)
    chat["last_message_id"] = latest["id"]
    chat["last_message_date"] = latest["date"]
    upsert_chat(db, chat)
    db.execute(
        "INSERT OR REPLACE INTO sync_state(key, value) VALUES (?, ?)",
        (f"messages_synced_at:{chat_peer_id}", fetched_at),
    )
    db.commit()
    return chat, cached_message(db, chat_peer_id, trigger.id)


def emit(kind: str, chat: dict[str, Any], message: dict[str, Any]) -> None:
    print(json.dumps({
        "kind": kind,
        "chat": {
            "peer_id": chat["peer_id"],
            "title": chat["title"],
            "username": chat["username"],
        },
        "message": message,
    }, ensure_ascii=False), flush=True)


async def listen(args: argparse.Namespace) -> None:
    db = connect_write(args.db)
    client = TelegramClient(
        session_base(args.session),
        api=API.TelegramDesktop,
        receive_updates=True,
        catch_up=True,
        sequential_updates=True,
    )
    lock = asyncio.Lock()

    async def on_message(event: events.NewMessage.Event) -> None:
        async with lock:
            entity = await event.get_chat()
            if entity is None:
                entity = await client.get_entity(event.message.peer_id)
            chat, message = await sync_chat(
                db,
                client,
                entity,
                event.message,
                args.local_files_dir,
                args.local_files_dir_source,
            )
            if message is not None:
                emit("message", chat, message)

    async def on_reaction(update: UpdateMessageReactions) -> None:
        async with lock:
            entity = await client.get_entity(update.peer)
            chat_peer_id = utils.get_peer_id(entity)
            before = reaction_state(cached_message(db, chat_peer_id, update.msg_id))
            message = await client.get_messages(entity, ids=update.msg_id)
            if message is None:
                return
            chat, current = await sync_chat(
                db,
                client,
                entity,
                message,
                args.local_files_dir,
                args.local_files_dir_source,
            )
            if current is None or not current["out"]:
                return
            if reaction_state(current) != before:
                emit("reaction", chat, current)

    # No direction filter: callers receive both incoming and outgoing messages.
    client.add_event_handler(on_message, events.NewMessage())
    client.add_event_handler(on_reaction, events.Raw(UpdateMessageReactions))
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise RuntimeError("session is not authorized")
        await client.run_until_disconnected()
    finally:
        await client.disconnect()
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--local-files-dir", action="append", default=[])
    parser.add_argument("--local-files-dir-source")
    args = parser.parse_args()
    logging.basicConfig(
        format="[%(levelname)s %(asctime)s] %(name)s: %(message)s",
        level=logging.WARNING,
    )
    try:
        asyncio.run(listen(args))
    except KeyboardInterrupt:
        pass
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
