# tg

Local Telegram history access for agents.

![alt text](image-1.png)

The goal is a local, read-only CLI/skill that lets an agent query Telegram history without interactive login.

**Depends on Telegram Desktop being logged in on the same machine**. `tg` bootstraps a separate auth session from Telegram Desktop `tdata`, syncs selected history into a local SQLite cache, and serves read commands from that cache.

## Setup

Requires Node `>=23.6.0` for native TypeScript stripping, plus Python 3 managed through `uv`.

Clone this repository, then run install commands:

```bash
git clone git@github.com:mitschabaude/tg.git
cd tg
uv sync
npm install
npm link
```

`npm link` installs the `tg` command globally as a symlink to this checkout. Keep this checkout in place; the CLI runs Python helpers through `uv`.

## Auth Bootstrap

```bash
tg auth bootstrap
```

`tg auth bootstrap` looks for Telegram Desktop `tdata` in common Linux and macOS locations. If detection fails, pass the path explicitly:

```bash
tg auth bootstrap --tdata ~/.local/share/TelegramDesktop/tdata
tg auth bootstrap --tdata ~/Library/Application\ Support/Telegram\ Desktop/tdata
```

The path must point at the `tdata` directory itself, not its parent `TelegramDesktop` directory.

Bootstrap copies `tdata` through a snapshot under `tmp/`, uses the Desktop authorization once to approve a QR-login token, and stores a separate Telethon session under `data/sessions/`. It also stores session metadata such as Telegram Desktop's effective downloads directory.

This is intentionally different from directly reusing TG Desktop's auth key. The agent session is a separate server-side authorization, so that sync operations don't mess with your TG Desktop client state.

## Sync And Read

```bash
tg sync chats --limit 100
tg chats list --limit 30

tg sync messages --chat <peer-id-or-username> --limit 1000
tg sync messages --chat <peer-id-or-username> --offset 100 --limit 100
tg sync messages --chat <peer-id-or-username> --full

tg messages list --chat <peer-id-or-username> --limit 20
tg messages list --chat <peer-id-or-username> --offset 100 --limit 100
tg cache status
```

Network/API access is explicit and only happens under `tg sync ...`. `chats list`, `messages list`, and `cache status` read only the local SQLite cache. Add `--json` to read commands for structured output.

The cache is sensitive account data. Sync creates `data/cache/` with `0700` permissions and SQLite files with `0600` permissions. Pure read commands do not create or initialize a missing cache; they print the relevant `tg sync ...` hint instead.

For `--chat`, use the canonical `peer_id` printed by `tg chats list`. Do not drop the minus sign: private/group peer ids can be negative, and the positive Telegram object id is not accepted as an alias.

Offsets are zero-based and counted from newest to oldest. For example, `messages list --offset 100 --limit 100` returns cached messages 100 through 199, and `sync messages --offset 100 --limit 100` fetches the same window from Telegram. `chats list` also accepts `--offset` for paging cached dialog results.

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
