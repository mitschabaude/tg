#!/usr/bin/env python3
import argparse
import asyncio
import json
import logging
import sqlite3
import sys
from uuid import uuid4
from typing import Any

from opentele.api import API
from opentele.tl import TelegramClient
from telethon import events, utils
from telethon.tl.types import UpdateMessageReactions, Chat, Channel

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
    trigger: Any | None,
    local_files_dir: list[str],
    local_files_dir_source: str | None,
    refresh: bool = False,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    chat_peer_id = utils.get_peer_id(entity)
    newest = db.execute(
        "SELECT MAX(id) FROM messages WHERE chat_peer_id = ?",
        (chat_peer_id,),
    ).fetchone()[0]
    fetched_at = now_iso()

    if newest is None or refresh:
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

    if trigger is not None and not any(message.id == trigger.id for message in messages):
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
    chat["last_message_id"] = latest["id"] if latest else None
    chat["last_message_date"] = latest["date"] if latest else None
    upsert_chat(db, chat)
    db.execute(
        "INSERT OR REPLACE INTO sync_state(key, value) VALUES (?, ?)",
        (f"messages_synced_at:{chat_peer_id}", fetched_at),
    )
    db.commit()
    return chat, cached_message(db, chat_peer_id, trigger.id) if trigger else None


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


def is_member_group(entity: Any) -> bool:
    return (isinstance(entity, Chat) or isinstance(entity, Channel) and entity.megagroup) and not (
        getattr(entity, "left", False) or getattr(entity, "kicked", False)
        or getattr(entity, "deactivated", False)
        or getattr(entity, "migrated_to", None)
    )


class Memberships:
    def __init__(self, db: sqlite3.Connection):
        self.db = db
        db.execute("CREATE TABLE IF NOT EXISTS event_memberships (peer_id INTEGER PRIMARY KEY, active INTEGER NOT NULL, pending_id TEXT)")
        self.ready = db.execute("SELECT 1 FROM sync_state WHERE key = 'event_memberships_initialized'").fetchone() is not None

    def baseline(self, ids: set[int]) -> None:
        with self.db:
            for peer_id in ids:
                self.db.execute("INSERT OR IGNORE INTO event_memberships VALUES (?, 1, NULL)", (peer_id,))
            self.db.execute("INSERT OR REPLACE INTO sync_state VALUES ('event_memberships_initialized', ?)", (now_iso(),))
        self.ready = True

    def join(self, peer_id: int) -> str | None:
        row = self.db.execute("SELECT active, pending_id FROM event_memberships WHERE peer_id = ?", (peer_id,)).fetchone()
        if row and row[0]:
            return row[1]
        event_id = f"tg/join/{peer_id}/{uuid4()}"
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO event_memberships VALUES (?, 1, ?)", (peer_id, event_id))
        return event_id

    def leave(self, peer_id: int) -> None:
        with self.db:
            self.db.execute("UPDATE event_memberships SET active = 0, pending_id = NULL WHERE peer_id = ?", (peer_id,))

    def delivered(self, peer_id: int) -> None:
        with self.db:
            self.db.execute("UPDATE event_memberships SET pending_id = NULL WHERE peer_id = ?", (peer_id,))


async def reconcile_memberships(db, client, memberships, joined) -> None:
    groups = {utils.get_peer_id(d.entity): d.entity async for d in client.iter_dialogs()
              if is_member_group(d.entity)}
    if not memberships.ready:
        memberships.baseline(set(groups))
        return
    for row in db.execute("SELECT peer_id FROM event_memberships WHERE active = 1").fetchall():
        if row[0] not in groups:
            memberships.leave(row[0])
    for entity in groups.values():
        await joined(entity)


async def handle_membership(event, self_id, memberships, joined) -> None:
    if self_id not in (event.user_ids or []):
        return
    if event.user_left or event.user_kicked:
        memberships.leave(event.chat_id)
        return
    if not (event.user_added or event.user_joined or event.created):
        return
    entity = await event.get_chat()
    if not is_member_group(entity):
        return
    added_by = None
    if event.user_added:
        try:
            actor = await event.get_added_by()
            if actor and actor.id != self_id:
                added_by = utils.get_display_name(actor)
        except Exception:
            logging.warning("Could not resolve group inviter", exc_info=True)
    await joined(entity, added_by)


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
    memberships = Memberships(db)
    self_id = None

    async def joined(entity: Any, added_by: str | None = None) -> None:
        peer_id = utils.get_peer_id(entity)
        event_id = memberships.join(peer_id)
        if event_id is None:
            return
        chat, _ = await sync_chat(db, client, entity, None, args.local_files_dir,
                                  args.local_files_dir_source, refresh=True)
        print(json.dumps({"kind": "join", "id": event_id,
                          "chat": {k: chat[k] for k in ("peer_id", "title", "username")},
                          "added_by": added_by}, ensure_ascii=False), flush=True)
        memberships.delivered(peer_id)

    async def reconcile() -> None:
        # Only mark departures after a complete, successful dialog scan.
        async with lock:
            await reconcile_memberships(db, client, memberships, joined)

    async def on_membership(event: events.ChatAction.Event) -> None:
        async with lock:
            await handle_membership(event, self_id, memberships, joined)

    async def reconcile_loop() -> None:
        while True:
            await asyncio.sleep(300)
            try:
                await reconcile()
            except Exception:
                logging.exception("Group membership reconciliation failed; will retry")

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
        self_id = (await client.get_me()).id
        await reconcile()
        client.add_event_handler(on_membership, events.ChatAction())
        reconciliation = asyncio.create_task(reconcile_loop())
        try:
            await client.run_until_disconnected()
        finally:
            reconciliation.cancel()
            await asyncio.gather(reconciliation, return_exceptions=True)
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
