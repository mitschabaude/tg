# tg

Local Telegram history access for agents.

The goal is a local, read-only CLI/skill that lets an agent query Telegram history without interactive login. The initial direction is to bootstrap a separate API session from Telegram Desktop `tdata`, then sync accessible history into a local SQLite/FTS store for querying.

Own code is TypeScript. Python/other tools may still be used behind a small boundary if they are the best way to import or convert Telegram Desktop session data.

## Auth Import

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
npm install
npm run tg -- auth import
```

By default this imports from the snap Telegram Desktop `tdata` path, snapshots it under `tmp/`, derives a Telethon session under `data/sessions/`, stores session metadata, and prints non-secret account identity fields.

## Message Peek

```bash
npm run tg -- chats list --limit 30
npm run tg -- messages recent --chat <peer-id-or-username> --limit 20
```

Add `--json` to either command for structured output.

Plain text message output is compact and agent-friendly. When a known local attachment exists, it is rendered as:

```text
[pdf: /home/gregor/Downloads/Telegram Desktop/example.pdf (404 KiB)]
```

Use `--json` for full attachment metadata such as MIME type, Telegram file id, dimensions, download status, and `path_source`.
