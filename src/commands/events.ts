import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { createInterface } from "node:readline";
import { join } from "node:path";
import { readOption } from "../args.ts";
import { rootDir } from "../paths.ts";
import { cachePath, resolveSessionBase } from "../sessions.ts";
import { formatMessage, type MessageRow } from "./messages.ts";
import { resolveLocalFiles } from "./sync.ts";

type ChatRow = {
  peer_id: number;
  title: string;
  username: string | null;
};

export type ListenerRow = {
  kind: "message" | "reaction";
  chat: ChatRow;
  message: MessageRow;
};

export async function runEventsListen(
  args: string[],
  usage: () => never,
): Promise<void> {
  const sessionName = parseSession(args, usage);
  const localFiles = resolveLocalFiles(sessionName);
  const child = spawn("uv", [
    "run",
    "python",
    join(rootDir, "scripts/telegram_events.py"),
    "--db",
    cachePath(sessionName),
    "--session",
    resolveSessionBase(sessionName),
    ...localFiles.dirs.flatMap((dir) => ["--local-files-dir", dir]),
    ...(localFiles.source ? ["--local-files-dir-source", localFiles.source] : []),
  ], {
    cwd: rootDir,
    stdio: ["ignore", "pipe", "inherit"],
  });
  const exited = new Promise<number | null>((resolve, reject) => {
    child.once("error", reject);
    child.once("exit", resolve);
  });
  const stop = () => child.kill();
  process.once("SIGINT", stop);
  process.once("SIGTERM", stop);

  try {
    const lines = createInterface({ input: child.stdout });
    for await (const line of lines) {
      if (!line.trim()) continue;
      const event = JSON.parse(line) as ListenerRow;
      process.stdout.write(`${JSON.stringify(formatEvent(event))}\n`);
    }
  } finally {
    process.off("SIGINT", stop);
    process.off("SIGTERM", stop);
  }

  const code = await exited;
  if (code !== 0) process.exitCode = code ?? 1;
}

export function formatEvent(event: ListenerRow): { id: string; body: string } {
  const chat = formatChat(event.chat);
  const message = formatMessage(event.message, { wrap: false });
  const context = `Context is synced. Inspect with:\ntg messages list --chat ${event.chat.peer_id} --limit 20`;

  if (event.kind === "message") {
    const heading = event.message.out ? "Outgoing Telegram message" : "Telegram message";
    return {
      id: `tg/message/${event.chat.peer_id}/${event.message.id}`,
      body: `${heading}\nChat: ${chat}\n\n${message}\n\n${context}`,
    };
  }

  const reactions = event.message.reaction_counts.length
    ? ""
    : "\n\nCurrent reactions: none";
  const state = JSON.stringify({
    counts: event.message.reaction_counts,
    recent: event.message.recent_reactions,
  });
  const digest = createHash("sha256").update(state).digest("hex").slice(0, 16);
  return {
    id: `tg/reaction/${event.chat.peer_id}/${event.message.id}/${digest}`,
    body: `Telegram reaction update\nChat: ${chat}\n\n${message}${reactions}\n\n${context}`,
  };
}

function parseSession(args: string[], usage: () => never): string {
  let sessionName = "default";
  for (let index = 0; index < args.length; index += 1) {
    if (args[index] !== "--session") usage();
    sessionName = readOption(args, index, usage);
    index += 1;
  }
  return sessionName;
}

function formatChat(chat: ChatRow): string {
  const username = chat.username ? ` (@${chat.username})` : "";
  return `${chat.title}${username} [${chat.peer_id}]`;
}
