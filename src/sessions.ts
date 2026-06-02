import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { rootDir } from "./paths.ts";
import { sanitizeName } from "./args.ts";

export type SessionMetadata = {
  telegram_desktop?: {
    download_directory?: {
      path: string | null;
      source: string;
      available: boolean;
    };
  };
};

export function resolveSessionBase(name: string): string {
  const safe = sanitizeName(name, "session name");
  const base = join(rootDir, "data", "sessions", safe);
  const file = `${base}.session`;
  if (!existsSync(file)) {
    console.error(`session not found: ${file}`);
    console.error("run: npm run tg -- auth bootstrap");
    process.exit(1);
  }
  return base;
}

export function sessionMetadataPath(name: string): string {
  const safe = sanitizeName(name, "session name");
  return join(rootDir, "data", "sessions", `${safe}.metadata.json`);
}

export function readSessionMetadata(name: string): SessionMetadata | null {
  const path = sessionMetadataPath(name);
  if (!existsSync(path)) {
    return null;
  }
  return JSON.parse(readFileSync(path, "utf8")) as SessionMetadata;
}
