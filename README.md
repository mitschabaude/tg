# tg

Local Telegram history access for agents.

The goal is a local, read-only CLI/skill that lets an agent query Telegram history without interactive login. The initial direction is to bootstrap a separate API session from Telegram Desktop `tdata`, then sync accessible history into a local SQLite/FTS store for querying.

Own code is TypeScript. Python/other tools may still be used behind a small boundary if they are the best way to import or convert Telegram Desktop session data.

## Auth Probe

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
npm install
npm run tg -- auth probe
```

By default this probes the snap Telegram Desktop `tdata` path, snapshots it under `tmp/`, derives a Telethon session under `data/sessions/`, and prints non-secret account identity fields.

