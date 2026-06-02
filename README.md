# tg

Local Telegram history access for agents.

The goal is a local, read-only CLI/skill that lets an agent query Telegram history without interactive login. The initial direction is to bootstrap a separate API session from Telegram Desktop `tdata`, then sync accessible history into a local SQLite/FTS store for querying.

Own code is TypeScript. Python/other tools may still be used behind a small boundary if they are the best way to import or convert Telegram Desktop session data.

## Auth Bootstrap

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
npm install
npm run tg -- auth bootstrap
```

By default this reads from the snap Telegram Desktop `tdata` path through a snapshot under `tmp/`, uses the Desktop authorization once to approve a QR-login token, and stores a separate Telethon session under `data/sessions/`. It also stores session metadata such as Telegram Desktop's effective downloads directory.

This is intentionally different from directly reusing Telegram Desktop's auth key. Older experiments used `UseCurrentSession`, which made the agent session act as the same server-side authorization as Telegram Desktop. Do not use those shared-auth sessions for message queries; bootstrap a fresh `default.session` instead and retire old files such as `probe.session`.

If Telegram Desktop appears to stop loading older uncached history after experiments, fully quitting and restarting Telegram Desktop is the first recovery step. In our test, older history reappeared after restart.

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
