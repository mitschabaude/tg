# tg

Local Telegram history access for agents.

The goal is a local, read-only CLI/skill that lets an agent query Telegram history without interactive login. It bootstraps a separate API session from Telegram Desktop `tdata`, syncs selected history into a local SQLite cache, and serves read commands from that cache.

Own code is TypeScript. Python/other tools may still be used behind a small boundary if they are the best way to import or convert Telegram Desktop session data.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
npm install
npm link
```

`npm link` installs the `tg` command globally as a symlink to this checkout. Keep this checkout and its `.venv` in place; the CLI uses the repo-local Python environment.

Requires a Node version with native TypeScript stripping support.

## Auth Bootstrap

```bash
tg auth bootstrap
```

By default this reads from the snap Telegram Desktop `tdata` path through a snapshot under `tmp/`, uses the Desktop authorization once to approve a QR-login token, and stores a separate Telethon session under `data/sessions/`. It also stores session metadata such as Telegram Desktop's effective downloads directory.

This is intentionally different from directly reusing Telegram Desktop's auth key. The agent session should be a separate server-side authorization from Telegram Desktop, not a shared-auth session.

## Sync And Read

```bash
tg sync chats --limit 100
tg sync messages --chat <peer-id-or-username> --limit 1000
tg sync messages --chat <peer-id-or-username> --offset 100 --limit 100
tg sync messages --chat <peer-id-or-username> --full

tg chats list --limit 30
tg messages list --chat <peer-id-or-username> --limit 20
tg messages list --chat <peer-id-or-username> --offset 100 --limit 100
tg cache status
```

Network/API access is explicit and only happens under `tg sync ...`. `chats list`, `messages list`, and `cache status` read only the local SQLite cache. Add `--json` to read commands for structured output.

The cache is sensitive account data. Sync creates `data/cache/` with `0700` permissions and SQLite files with `0600` permissions. Pure read commands do not create or initialize a missing cache; they print the relevant `tg sync ...` hint instead.

`sync messages --full --offset N` means sync all older messages after skipping the newest `N`. `--full` cannot be combined with `--limit`.

For `--chat`, use the canonical `peer_id` printed by `tg chats list`. Do not drop the minus sign: private/group peer ids can be negative, and the positive Telegram object id is not accepted as an alias.

For `messages list`, offset is zero-based from newest message first: `--offset 100 --limit 100` returns messages 100 through 199. `chats list` also accepts `--offset` for paging cached dialog results.

Plain text message output is compact and agent-friendly. When a known local attachment exists, it is rendered as:

```text
[pdf: /path/to/Telegram Desktop/example.pdf (404 KiB)]
```

Use `--json` for full attachment metadata such as MIME type, Telegram file id, dimensions, download status, and `path_source`.
