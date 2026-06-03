import { readOption } from "../args.ts";
import { runJsonHelper } from "../python.ts";
import { cachePath } from "../sessions.ts";

type CacheStatus = {
  db: string;
  chats: {
    count: number;
    synced_at: string | null;
  };
  peers: {
    count: number;
  };
  messages: {
    count: number;
    chats: Array<{
      chat_peer_id: number;
      title: string | null;
      count: number;
      newest: string | null;
      oldest: string | null;
      synced_at: string | null;
    }>;
  };
};

export function runCacheStatus(args: string[], usage: () => never): void {
  const options = parseCacheStatusOptions(args, usage);
  const status = runJsonHelper<CacheStatus>("scripts/telegram_cache.py", [
    "cache-status",
    "--db", cachePath(options.sessionName),
  ]);

  if (options.json) {
    console.log(JSON.stringify(status, null, 2));
    return;
  }

  console.log(`db: ${status.db}`);
  console.log(`chats: ${status.chats.count}${status.chats.synced_at ? ` synced_at=${status.chats.synced_at}` : ""}`);
  console.log(`peers: ${status.peers.count}`);
  console.log(`messages: ${status.messages.count}`);
  for (const chat of status.messages.chats) {
    const title = chat.title ? ` ${chat.title}` : "";
    console.log(`${chat.chat_peer_id}${title}\t${chat.count}\tnewest=${chat.newest ?? ""}\toldest=${chat.oldest ?? ""}`);
  }
}

function parseCacheStatusOptions(args: string[], usage: () => never): { sessionName: string; json: boolean } {
  let sessionName = "default";
  let json = false;

  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    switch (arg) {
      case "--session":
        sessionName = readOption(args, index, usage);
        index += 1;
        break;
      case "--json":
        json = true;
        break;
      default:
        usage();
    }
  }

  return { sessionName, json };
}
