# tg

Telegram read access for agents. Linux and Mac. No login dance.

![alt text](image-1.png)

**Depends on Telegram Desktop being logged in on the same machine**. `tg` bootstraps a separate auth session from Telegram Desktop `tdata`, syncs selected history into a local SQLite cache, and serves read commands from that cache.

## Usage

Just install the [skill](https://github.com/mitschabaude/tg/tree/main/skills/tg) and ask your agent about your TG messages!

Requirements: Linux or Mac, git, Telegram Desktop, Node `>=23.6.0`, Python 3 with `uv`.

## How it works

`tg auth bootstrap` looks for Telegram Desktop `tdata` in common Linux and macOS locations. It copies `tdata` through a snapshot under `tmp/`, uses the Desktop authorization once to approve a QR-login token, and stores a separate Telethon session under `data/sessions/`. It also stores session metadata such as Telegram Desktop's effective downloads directory.

This is intentionally different from directly reusing TG Desktop's auth key. The agent session is a separate server-side authorization, so that sync operations don't mess with your TG Desktop client state.

After bootstrap, `tg sync` commands use the persistent client session to fetch chats/messages into a fast local SQLite cache, which serves all read requests like `tg messages list`. See the [skill](https://github.com/mitschabaude/tg/tree/main/skills/tg) for the list of available commands.

## Live events

`tg events listen --session NAME` keeps a Telegram connection open and writes one concise JSONL event for each message. Before emitting an event, it updates the affected chat in the local cache: existing chats are synchronized from their newest cached message, while new chats receive the latest 100 messages of context.

Reaction changes are cached as well. They produce events only when they affect messages sent by the logged-in user.

The command is intended to run as a supervised service. Its stdout is the event stream and diagnostics go to stderr.

> [!WARNING]
> The local client session under `data/sessions/` gives an attacker Telegram account access equivalent to a locally logged-in Telegram Desktop client. The local cache under `data/cache/` can also contain sensitive message history. Treat both as private account data.
