#!/usr/bin/env node
import { runAuthBootstrap } from "./commands/authBootstrap.ts";
import { runCacheStatus } from "./commands/cache.ts";
import { runChatsList } from "./commands/chats.ts";
import { runMessagesList } from "./commands/messages.ts";
import { runSyncChats, runSyncMessages } from "./commands/sync.ts";

function usage(): never {
  console.error(`Usage:
  tg auth bootstrap [--tdata PATH] [--session NAME] [--passcode PASSCODE] [--password TELEGRAM_2FA_PASSWORD] [--keep-snapshot]
  tg sync chats [--session NAME] [--limit N]
  tg sync messages --chat CHAT [--session NAME] [--limit N] [--offset N]
  tg sync messages --chat CHAT [--session NAME] --full
  tg chats list [--session NAME] [--limit N] [--offset N] [--json]
  tg messages list --chat CHAT [--session NAME] [--limit N] [--offset N] [--json]
  tg cache status [--session NAME] [--json]

Default tdata path:
  ~/snap/telegram-desktop/current/.local/share/TelegramDesktop/tdata`);
  process.exit(2);
}

const args = process.argv.slice(2);

if (args[0] === "auth" && args[1] === "bootstrap") {
  runAuthBootstrap(args.slice(2), usage);
} else if (args[0] === "sync" && args[1] === "chats") {
  runSyncChats(args.slice(2), usage);
} else if (args[0] === "sync" && args[1] === "messages") {
  runSyncMessages(args.slice(2), usage);
} else if (args[0] === "chats" && args[1] === "list") {
  runChatsList(args.slice(2), usage);
} else if (args[0] === "messages" && args[1] === "list") {
  runMessagesList(args.slice(2), usage);
} else if (args[0] === "cache" && args[1] === "status") {
  runCacheStatus(args.slice(2), usage);
} else {
  usage();
}
