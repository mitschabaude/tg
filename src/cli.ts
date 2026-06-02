#!/usr/bin/env node
import { runAuthBootstrap } from "./commands/authBootstrap.ts";
import { runChatsList } from "./commands/chats.ts";
import { runMessagesRecent } from "./commands/messages.ts";

function usage(): never {
  console.error(`Usage:
  tg auth bootstrap [--tdata PATH] [--session NAME] [--passcode PASSCODE] [--password TELEGRAM_2FA_PASSWORD] [--keep-snapshot]
  tg chats list [--session NAME] [--limit N] [--json]
  tg messages recent --chat CHAT [--session NAME] [--limit N] [--json] [--local-files-dir PATH] [--download-attachments] [--max-attachment-mb N]

Default tdata path:
  ~/snap/telegram-desktop/current/.local/share/TelegramDesktop/tdata`);
  process.exit(2);
}

const args = process.argv.slice(2);

if (args[0] === "auth" && args[1] === "bootstrap") {
  runAuthBootstrap(args.slice(2), usage);
} else if (args[0] === "chats" && args[1] === "list") {
  runChatsList(args.slice(2), usage);
} else if (args[0] === "messages" && args[1] === "recent") {
  runMessagesRecent(args.slice(2), usage);
} else {
  usage();
}
