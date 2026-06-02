import { parseLimit, readOption } from "../args.ts";
import { runJsonHelper } from "../python.ts";
import { resolveSessionBase } from "../sessions.ts";

type MessageRow = {
  id: number;
  date: string | null;
  sender_id: number | null;
  text: string;
  out: boolean;
  post: boolean;
  reply_to_msg_id: number | null;
};

type MessagesRecentOptions = {
  sessionName: string;
  chat: string;
  limit: number;
  json: boolean;
};

export function runMessagesRecent(args: string[], usage: () => never): void {
  const options = parseMessagesRecentOptions(args, usage);
  const rows = runJsonHelper<MessageRow[]>("scripts/telegram_peek.py", [
    "messages-recent",
    "--session", resolveSessionBase(options.sessionName),
    "--chat", options.chat,
    "--limit", String(options.limit),
  ]);

  if (options.json) {
    console.log(JSON.stringify(rows, null, 2));
  } else {
    for (const row of rows) {
      const date = row.date ?? "";
      const sender = row.sender_id ? ` sender=${row.sender_id}` : "";
      const reply = row.reply_to_msg_id ? ` reply=${row.reply_to_msg_id}` : "";
      const text = row.text.replace(/\s+/g, " ").trim();
      console.log(`${row.id}\t${date}${sender}${reply}\t${text}`);
    }
  }
}

function parseMessagesRecentOptions(args: string[], usage: () => never): MessagesRecentOptions {
  let sessionName = "probe";
  let chat = "";
  let limit = 20;
  let json = false;

  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    switch (arg) {
      case "--session":
        sessionName = readOption(args, index, usage);
        index += 1;
        break;
      case "--chat":
        chat = readOption(args, index, usage);
        index += 1;
        break;
      case "--limit":
        limit = parseLimit(readOption(args, index, usage), usage);
        index += 1;
        break;
      case "--json":
        json = true;
        break;
      default:
        usage();
    }
  }

  if (!chat) {
    usage();
  }
  return { sessionName, chat, limit, json };
}

