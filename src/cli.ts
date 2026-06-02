#!/usr/bin/env tsx
import { runAuthProbe } from "./commands/authProbe.js";

function usage(): never {
  console.error(`Usage:
  tg auth probe [--tdata PATH] [--session NAME] [--passcode PASSCODE] [--keep-snapshot]

Default tdata path:
  ~/snap/telegram-desktop/current/.local/share/TelegramDesktop/tdata`);
  process.exit(2);
}

const args = process.argv.slice(2);

if (args[0] === "auth" && args[1] === "probe") {
  runAuthProbe(args.slice(2), usage);
} else {
  usage();
}
