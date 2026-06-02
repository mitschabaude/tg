import { parseLimit, parseOffset, readOption } from "../args.ts";
import { runJsonHelper } from "../python.ts";
import { cachePath } from "../sessions.ts";

type ChatRow = {
  peer_id: number;
  id: number;
  type: string;
  title: string;
  username: string | null;
  unread_count: number;
};

type ChatsListOptions = {
  sessionName: string;
  limit: number;
  offset: number;
  json: boolean;
};

export function runChatsList(args: string[], usage: () => never): void {
  const options = parseChatsListOptions(args, usage);
  const rows = runJsonHelper<ChatRow[]>("scripts/telegram_cache.py", [
    "list-chats",
    "--db", cachePath(options.sessionName),
    "--limit", String(options.limit),
    "--offset", String(options.offset),
  ]);

  if (options.json) {
    console.log(JSON.stringify(rows, null, 2));
  } else {
    for (const row of rows) {
      const username = row.username ? ` @${row.username}` : "";
      const unread = row.unread_count ? ` unread=${row.unread_count}` : "";
      console.log(`${row.peer_id}\t${row.type}\t${row.title}${username}${unread}`);
    }
  }
}

function parseChatsListOptions(args: string[], usage: () => never): ChatsListOptions {
  let sessionName = "default";
  let limit = 30;
  let offset = 0;
  let json = false;

  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    switch (arg) {
      case "--session":
        sessionName = readOption(args, index, usage);
        index += 1;
        break;
      case "--limit":
        limit = parseLimit(readOption(args, index, usage), usage);
        index += 1;
        break;
      case "--offset":
        offset = parseOffset(readOption(args, index, usage), usage);
        index += 1;
        break;
      case "--json":
        json = true;
        break;
      default:
        usage();
    }
  }

  return { sessionName, limit, offset, json };
}
