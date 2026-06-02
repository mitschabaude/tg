import { parseLimit, parseOffset, readOption } from "../args.ts";
import { runJsonHelper } from "../python.ts";
import { cachePath } from "../sessions.ts";

type MessageRow = {
  id: number;
  date: string | null;
  sender_id: number | null;
  text: string;
  out: boolean;
  post: boolean;
  reply_to_msg_id: number | null;
  attachments: AttachmentRow[];
};

type AttachmentRow = {
  index: number;
  kind: string;
  name: string | null;
  mime_type: string | null;
  size: number | null;
  ext: string | null;
  file_id: string | null;
  width: number | null;
  height: number | null;
  duration: number | null;
  path: string | null;
  downloaded: boolean;
  download_skipped: string | null;
  download_error: string | null;
  path_source: string | null;
};

type MessagesRecentOptions = {
  sessionName: string;
  chat: string;
  limit: number;
  offset: number;
  json: boolean;
};

export function runMessagesList(args: string[], usage: () => never): void {
  const options = parseMessagesRecentOptions(args, usage);
  const rows = runJsonHelper<MessageRow[]>("scripts/telegram_cache.py", [
    "list-messages",
    "--db", cachePath(options.sessionName),
    "--chat", options.chat,
    "--limit", String(options.limit),
    "--offset", String(options.offset),
  ]);

  if (options.json) {
    console.log(JSON.stringify(rows, null, 2));
  } else {
    for (const row of rows) {
      const date = row.date ?? "";
      const sender = row.sender_id ? ` sender=${row.sender_id}` : "";
      const reply = row.reply_to_msg_id ? ` reply=${row.reply_to_msg_id}` : "";
      const text = row.text.replace(/\s+/g, " ").trim();
      const attachments = formatAttachments(row.attachments);
      console.log(`${row.id}\t${date}${sender}${reply}\t${[text, attachments].filter(Boolean).join(" ")}`);
    }
  }
}

function formatAttachments(attachments: AttachmentRow[]): string {
  if (!attachments.length) {
    return "";
  }
  return attachments.map((attachment) => {
    const name = attachment.path ?? attachment.name ?? attachment.ext ?? attachment.kind;
    const details = [
      attachment.size ? formatSize(attachment.size) : "",
      attachment.path ? "" : attachment.mime_type,
      formatDimensions(attachment),
      attachment.duration ? `${attachment.duration}s` : "",
    ].filter(Boolean).join(", ");
    const path = attachment.path ? "" : formatPath(attachment);
    const suffix = [details ? `(${details})` : "", path].filter(Boolean).join(" ");
    return suffix
      ? `[${attachment.kind}: ${name} ${suffix}]`
      : `[${attachment.kind}: ${name}]`;
  }).join(" ");
}

function formatPath(attachment: AttachmentRow): string {
  if (attachment.path) {
    return `path=${attachment.path}`;
  }
  if (attachment.download_error) {
    return `download_error=${JSON.stringify(attachment.download_error)}`;
  }
  if (attachment.download_skipped) {
    return `download_skipped=${attachment.download_skipped}`;
  }
  return "";
}

function formatSize(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${Math.round(bytes / 1024)} KiB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`;
}

function formatDimensions(attachment: AttachmentRow): string {
  return attachment.width && attachment.height
    ? `${attachment.width}x${attachment.height}`
    : "";
}

function parseMessagesRecentOptions(args: string[], usage: () => never): MessagesRecentOptions {
  let sessionName = "default";
  let chat = "";
  let limit = 20;
  let offset = 0;
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

  if (!chat) {
    usage();
  }
  return {
    sessionName,
    chat,
    limit,
    offset,
    json,
  };
}
