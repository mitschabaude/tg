# Rough Plan

1. Use production Telegram Desktop as the source of an already-authenticated local session.
2. Snapshot `tdata` read-only and import/convert the Telegram Desktop auth into a separate client session.
3. Use that separate session to sync Telegram history through the Telegram API, not by reading Desktop message cache.
4. Store synced chats, senders, messages, and raw metadata in a local SQLite database with full-text search.
5. Expose a small TypeScript CLI for agents: list chats, sync selected chats, search messages, show recent messages, and show context around a message.
6. Keep the agent-facing surface read-only by default. Sending or mutating Telegram state is out of scope unless added explicitly later.
7. Treat `tdata` and derived sessions as account credentials: never write to production `tdata`, avoid logging secrets, and keep local files permission-locked.

