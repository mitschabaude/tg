# tg

Local Telegram history access for agents.

The goal is a local, read-only CLI/skill that lets an agent query Telegram history without interactive login. The initial direction is to bootstrap a separate API session from Telegram Desktop `tdata`, then sync accessible history into a local SQLite/FTS store for querying.

Own code is TypeScript. Python/other tools may still be used behind a small boundary if they are the best way to import or convert Telegram Desktop session data.

