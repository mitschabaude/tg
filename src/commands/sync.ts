import { parseLimit, parseOffset, readOption } from "../args.ts";
import { runJsonHelper } from "../python.ts";
import { cachePath, readSessionMetadata, resolveSessionBase } from "../sessions.ts";

type SyncChatsOptions = {
  sessionName: string;
  limit: number;
};

type SyncMessagesOptions = {
  sessionName: string;
  chat: string;
  limit: number;
  offset: number;
  full: boolean;
};

type SyncResult = {
  synced_chats?: number;
  synced_messages?: number;
  chat?: number;
  synced_at: string;
};

export function runSyncChats(args: string[], usage: () => never): void {
  const options = parseSyncChatsOptions(args, usage);
  const result = runJsonHelper<SyncResult>("scripts/telegram_cache.py", [
    "sync-chats",
    "--db", cachePath(options.sessionName),
    "--session", resolveSessionBase(options.sessionName),
    "--limit", String(options.limit),
  ]);
  console.log(`synced_chats: ${result.synced_chats ?? 0}`);
  console.log(`synced_at: ${result.synced_at}`);
}

export function runSyncMessages(args: string[], usage: () => never): void {
  const options = parseSyncMessagesOptions(args, usage);
  const localFiles = resolveLocalFiles(options.sessionName);
  const result = runJsonHelper<SyncResult>("scripts/telegram_cache.py", [
    "sync-messages",
    "--db", cachePath(options.sessionName),
    "--session", resolveSessionBase(options.sessionName),
    "--chat", options.chat,
    ...(options.full ? ["--full"] : ["--limit", String(options.limit)]),
    "--offset", String(options.offset),
    ...localFiles.dirs.flatMap((dir) => ["--local-files-dir", dir]),
    ...(localFiles.source ? ["--local-files-dir-source", localFiles.source] : []),
  ]);
  console.log(`chat: ${result.chat ?? options.chat}`);
  console.log(`synced_messages: ${result.synced_messages ?? 0}`);
  console.log(`synced_at: ${result.synced_at}`);
}

function parseSyncChatsOptions(args: string[], usage: () => never): SyncChatsOptions {
  let sessionName = "default";
  let limit = 100;

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
      default:
        usage();
    }
  }

  return { sessionName, limit };
}

function parseSyncMessagesOptions(args: string[], usage: () => never): SyncMessagesOptions {
  let sessionName = "default";
  let chat = "";
  let limit = 100;
  let offset = 0;
  let full = false;

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
      case "--offset":
        offset = parseOffset(readOption(args, index, usage), usage);
        index += 1;
        break;
      case "--full":
        full = true;
        break;
      default:
        usage();
    }
  }

  if (!chat) {
    usage();
  }
  return { sessionName, chat, limit, offset, full };
}

function resolveLocalFiles(sessionName: string): { dirs: string[]; source: string | null } {
  const metadata = readSessionMetadata(sessionName);
  const downloadDirectory = metadata?.telegram_desktop?.download_directory;
  if (!downloadDirectory?.available || !downloadDirectory.path) {
    return { dirs: [], source: null };
  }
  return {
    dirs: [downloadDirectory.path],
    source: downloadDirectory.source,
  };
}
