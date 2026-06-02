import { existsSync } from "node:fs";
import { join } from "node:path";
import { rootDir } from "./paths.ts";
import { sanitizeName } from "./args.ts";

export function resolveSessionBase(name: string): string {
  const safe = sanitizeName(name, "session name");
  const base = join(rootDir, "data", "sessions", safe);
  const file = `${base}.session`;
  if (!existsSync(file)) {
    console.error(`session not found: ${file}`);
    console.error("run: npm run tg -- auth probe");
    process.exit(1);
  }
  return base;
}

