import { parseLimit, parseOffset, readOption } from "../args.ts";
import { runJsonHelper } from "../python.ts";
import { cachePath } from "../sessions.ts";

type MessageRow = {
  id: number;
  date: string | null;
  sender_id: number | null;
  sender_title: string | null;
  sender_username: string | null;
  text: string;
  out: boolean;
  post: boolean;
  reply_to_msg_id: number | null;
  attachments: AttachmentRow[];
  reaction_counts: ReactionCountRow[];
  recent_reactions: RecentReactionRow[];
  reactions_complete: boolean;
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

type ReactionCountRow = {
  index: number;
  kind: string;
  emoticon: string | null;
  custom_emoji_document_id: string | null;
  count: number;
  chosen_order: number | null;
};

type RecentReactionRow = {
  index: number;
  reactor_peer_id: number | null;
  reactor_title: string | null;
  reactor_username: string | null;
  kind: string;
  emoticon: string | null;
  custom_emoji_document_id: string | null;
  date: string | null;
  big: boolean;
  unread: boolean;
  my: boolean;
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
  } else if (rows.length) {
    console.log(rows.map(formatMessage).join("\n\n"));
  }
}

function formatMessage(row: MessageRow): string {
  const lines = [formatHeader(row)];
  const width = messageWidth();
  const text = row.text.trim();
  if (text) {
    lines.push(...wrapText(text, width, "  "));
  }
  lines.push(...formatAttachments(row.attachments).flatMap((attachment) =>
    wrapText(attachment, width, "")));
  const reactions = formatReactions(row);
  if (reactions) {
    lines.push(...wrapText(reactions, width, ""));
  }
  return lines.join("\n");
}

function formatHeader(row: MessageRow): string {
  const label = bold(formatPeer(row.sender_id, row.sender_title, row.sender_username));
  const parts = [
    label,
    formatDate(row.date),
    `#${row.id}`,
    row.reply_to_msg_id ? `reply #${row.reply_to_msg_id}` : "",
  ].filter(Boolean);
  return parts.join("  ");
}

function bold(text: string): string {
  if (!supportsAnsiStyle()) {
    return text;
  }
  return `\x1b[1m${text}\x1b[22m`;
}

function italic(text: string): string {
  if (!supportsAnsiStyle()) {
    return text;
  }
  return `\x1b[3m${text}\x1b[23m`;
}

function supportsAnsiStyle(): boolean {
  if (process.env.NO_COLOR) {
    return false;
  }
  if (process.env.FORCE_COLOR && process.env.FORCE_COLOR !== "0") {
    return true;
  }
  return process.stdout.isTTY;
}

function formatPeer(peerId: number | null, title: string | null, username: string | null): string {
  if (title && username) {
    return `${title} (@${username})`;
  }
  if (title) {
    return title;
  }
  if (username) {
    return `@${username}`;
  }
  return peerId === null ? "unknown" : String(peerId);
}

function formatDate(value: string | null): string {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  const currentYear = new Date().getFullYear();
  const options: Intl.DateTimeFormatOptions = {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  };
  if (date.getFullYear() !== currentYear) {
    options.year = "numeric";
  }
  return new Intl.DateTimeFormat(undefined, options).format(date);
}

function formatAttachments(attachments: AttachmentRow[]): string[] {
  return attachments.map((attachment) => {
    const name = attachment.path ?? attachment.name ?? attachment.ext ?? attachment.kind;
    const details = [
      attachment.size ? formatSize(attachment.size) : "",
      formatDimensions(attachment),
      attachment.duration ? `${attachment.duration}s` : "",
    ].filter(Boolean).join(", ");
    const path = attachment.path ? "" : formatPath(attachment);
    const suffix = [details ? `(${details})` : "", path].filter(Boolean).join(" ");
    return suffix
      ? `${italic("attachment")}: ${attachment.kind} ${name} ${suffix}`
      : `${italic("attachment")}: ${attachment.kind} ${name}`;
  });
}

function formatReactions(row: MessageRow): string {
  if (!row.reaction_counts.length) {
    return "";
  }

  const recent = row.recent_reactions.map((reaction) => {
    const reactor = formatPeer(
      reaction.reactor_peer_id,
      reaction.reactor_title,
      reaction.reactor_username,
    );
    return `${reactor} ${formatReactionValue(reaction)}`;
  });
  if (row.reactions_complete && recent.length) {
    return `${italic("reactions")}: ${recent.join(", ")}`;
  }

  const counts = row.reaction_counts.map((reaction) =>
    `${formatReactionValue(reaction)}x${reaction.count}`);
  if (recent.length) {
    return `${italic("reactions")}: ${recent.join(", ")}; ${counts.join(" ")}`;
  }
  return `${italic("reactions")}: ${counts.join(" ")}`;
}

function formatReactionValue(reaction: ReactionCountRow | RecentReactionRow): string {
  if (reaction.emoticon) {
    return reaction.emoticon;
  }
  if (reaction.kind === "custom_emoji") {
    return `custom:${reaction.custom_emoji_document_id ?? "?"}`;
  }
  if (reaction.kind === "paid") {
    return "paid";
  }
  return reaction.kind;
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

function messageWidth(): number {
  const terminalWidth = process.stdout.columns ?? 100;
  return Math.max(40, Math.min(88, terminalWidth - 2));
}

function wrapText(text: string, width: number, indent: string): string[] {
  const paragraphs = text.split(/\r?\n/);
  const lines: string[] = [];
  for (const paragraph of paragraphs) {
    const trimmed = paragraph.trim();
    if (!trimmed) {
      lines.push("");
      continue;
    }
    lines.push(...wrapParagraph(trimmed, width, indent));
  }
  return lines;
}

function wrapParagraph(text: string, width: number, indent: string): string[] {
  const contentWidth = Math.max(20, width - indent.length);
  const lines: string[] = [];
  let line = "";
  for (const word of text.split(/\s+/)) {
    if (!line) {
      line = word;
      continue;
    }
    if (line.length + 1 + word.length <= contentWidth) {
      line += ` ${word}`;
      continue;
    }
    lines.push(...wrapLongLine(line, contentWidth, indent));
    line = word;
  }
  if (line) {
    lines.push(...wrapLongLine(line, contentWidth, indent));
  }
  return lines;
}

function wrapLongLine(line: string, width: number, indent: string): string[] {
  if (line.length <= width) {
    return [`${indent}${line}`];
  }
  const lines: string[] = [];
  for (let index = 0; index < line.length; index += width) {
    lines.push(`${indent}${line.slice(index, index + width)}`);
  }
  return lines;
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
