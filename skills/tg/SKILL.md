---
name: tg
description: Read Telegram chats and messages using `tg`. Use when asked to find, list, sync, or read Telegram history.
---

# Telegram CLI

Use the `tg` command to access Telegram history. It depends on Telegram Desktop being logged in on the same machine.

## Setup

If `tg` is missing, clone and install it:

```bash
git clone git@github.com:mitschabaude/tg.git
cd tg
uv sync
npm install
npm link
```

Setup requires Node `>=23.6.0`, Python 3, and `uv`. `npm link` installs `tg` globally as a symlink to this checkout; keep the checkout in place.

## Bootstrap

Only needed if no agent session exists. Check by running a normal command first:

```bash
tg cache status
```

If it reports a missing session, bootstrap one:

```bash
tg auth bootstrap
```

This snapshots Telegram Desktop `tdata`, uses the Desktop authorization once to approve a QR-login token, and stores a separate agent session. It auto-detects common Linux and macOS `tdata` paths; if that fails, pass the `tdata` directory explicitly:

```bash
tg auth bootstrap --tdata ~/.local/share/TelegramDesktop/tdata
tg auth bootstrap --tdata ~/Library/Application\ Support/Telegram\ Desktop/tdata
```

The path must point at the `tdata` directory itself, not its parent `TelegramDesktop` directory.

This intentionally creates a separate server-side authorization instead of directly reusing TG Desktop's auth key, so sync operations do not affect the TG Desktop client state.

## Sync and read chats/messages

Sync to get the latest chats and messages. After that, use the `chats` and `messages` read commands for fast local read from cached history.

```bash
tg sync chats --limit 100
tg chats list --limit 30

tg sync messages --chat CHAT --limit 1000
tg sync messages --chat CHAT --offset 100 --limit 100
tg sync messages --chat CHAT --full

tg messages list --chat CHAT --limit 20
tg messages list --chat CHAT --offset 100 --limit 100
tg cache status
```

`tg sync ...` commands use the network. `chats list`, `messages list`, and `cache status` are local-only cache reads.

For `--chat`, use the canonical `peer_id` printed by `tg chats list`. Do not drop the minus sign: private/group peer ids can be negative.

Offsets are zero-based and counted from newest to oldest. For example, `messages list --offset 100 --limit 100` returns cached messages 100 through 199, and `sync messages --offset 100 --limit 100` fetches the same window from Telegram. Default offset is 0.

Add `--json` to read commands only when verbose structured output is useful (prefer the default, plain-text output).

## Plain Output

Plain text message output is block-formatted for terminal reading: sender and time on the first line, wrapped message text below, then attachments and reactions as separate metadata lines. For example:

```text
Alex Example (@alex)  Jun 3, 12:45  #15005
  Hey how are you? Here is the report I promised.
attachment: pdf /path/to/Telegram Desktop/report.pdf (469 KiB)
reactions: Sam Example (@sam) 👍
```

Plain text includes full local attachment paths and is the preferred, token-efficient format for reading messages, for both humans and agents.

By comparison, `--json` is quite verbose. Use it when the output needs to be processed programmatically.

Message output uses cached peer names and usernames for senders and reactors when available, with numeric peer ids as a fallback. Re-syncing messages or chats fills in more peer metadata over time.
