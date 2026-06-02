# Rough Plan

1. Use production Telegram Desktop only as the zero-login bootstrap source. Snapshot `tdata`, approve a QR-login token, and store a separate agent session.
2. Network/API access is explicit and only happens under `tg sync ...`. Read commands are always local-cache reads.
3. Store synced chats, messages, attachments, sender metadata, raw JSON, and sync timestamps in local SQLite. Add FTS search after basic cached paging works.
4. Make sync idempotent: upsert by `(chat_id, message_id)`, refresh edited message fields when seen again, and defer robust deletion detection until contiguous sync windows are tracked.

## Commands

```bash
tg auth bootstrap

tg sync chats [--limit N]
tg sync messages --chat CHAT [--limit N] [--offset N]
tg sync messages --chat CHAT --full

tg chats list [--offset N] [--limit N] [--json]
tg messages list --chat CHAT [--offset N] [--limit N] [--json]

tg cache status
```

Later:

```bash
tg messages search --query TEXT [--chat CHAT] [--limit N] [--json]
```

## Behavior

- `tg chats list` and `tg messages list` never fetch from Telegram. If the cache is empty, print the relevant `tg sync ...` command.
- `--offset` is zero-based from newest first for messages. `--offset 100 --limit 100` returns messages 100 through 199.
- Attachments keep structured metadata and any known local file path, derived from Telegram Desktop download settings captured during bootstrap.
- Keep the agent-facing surface read-only. Sending or mutating Telegram state is out of scope unless added explicitly later.
- Treat `tdata`, derived sessions, and the cache as sensitive local account data: never write to production `tdata`, avoid logging secrets, and keep local files permission-locked.
