---
name: tg
description: Use the local Telegram CLI to inspect cached Telegram chats and messages. Use when asked to find, list, sync, or read Telegram history through the local `tg` command.
---

# Telegram CLI

Use the local `tg` command to access Telegram history. Reads are cache-only; network/API access only happens under `tg sync ...`.

## Setup Check

If `tg` is missing, run from the repo:

```bash
npm link
```

The command uses this checkout's `uv` Python environment. Setup requires Node `>=23.6.0`, Python 3, and `uv`; run `uv sync` from the repo if Python dependencies are missing.

## Bootstrap

Only needed if no agent session exists:

```bash
tg auth bootstrap
```

This snapshots Telegram Desktop `tdata`, uses the Desktop authorization once to approve a QR-login token, and stores a separate agent session. It auto-detects common Linux and macOS `tdata` paths; if that fails, pass the `tdata` directory explicitly with `--tdata PATH`.

## Sync

Sync before reading. These commands may use the network:

```bash
tg sync chats --limit 100
tg sync messages --chat CHAT --limit 1000
tg sync messages --chat CHAT --offset 100 --limit 100
tg sync messages --chat CHAT --full
```

`sync messages --full --offset N` syncs all older messages after skipping the newest `N`. `--full` cannot be combined with `--limit`.

## Read Cache

These commands are local-only:

```bash
tg chats list --limit 30
tg chats list --offset 30 --limit 30

tg messages list --chat CHAT --limit 20
tg messages list --chat CHAT --offset 100 --limit 100

tg cache status
```

Add `--json` to read commands when structured output is useful.

For `--chat`, use the canonical `peer_id` printed by `tg chats list`. Do not drop the minus sign: private/group peer ids can be negative, and the positive Telegram object id is not accepted as an alias.

For `messages list`, offset is zero-based from newest message first: `--offset 100 --limit 100` returns messages 100 through 199.

## Plain Output

Plain text message output is block-formatted for terminal reading: sender and time on the first line, wrapped message text below, then attachments and reactions as separate metadata lines. For example:

```text
Alex Example (@alex)  Jun 3, 12:45  #15005
  Here is the report including client response for the latest fix round!
attachment: pdf report.pdf (469 KiB)
reactions: Sam Example (@sam) 👍
```

Use `--json` for full attachment metadata such as MIME type, Telegram file id, dimensions, download status, and `path_source`.

Message sync stores reaction counts and Telegram's embedded recent reactor list. Small reaction sets may include individual reactors; larger sets may only include aggregate counts.

Message output uses cached peer names and usernames for senders and reactors when available, with numeric peer ids as a fallback.

## Safety

Treat `tdata`, sessions, and `data/cache/*.sqlite` as sensitive account data. Do not write to production `tdata`. Use the bootstrapped separate agent session rather than directly reusing Telegram Desktop authorization.
