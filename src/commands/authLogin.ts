import { chmodSync, existsSync } from "node:fs";
import { join } from "node:path";
import { rootDir } from "../paths.ts";
import { runInteractiveHelper } from "../python.ts";
import { sanitizeName } from "../args.ts";

type AuthLoginOptions = {
  sessionName: string;
  method: "qr" | "phone";
};

export function runAuthLogin(args: string[], usage: () => never): void {
  const options = parseAuthLoginOptions(args, usage);
  const sessionBase = join(rootDir, "data", "sessions", options.sessionName);

  runInteractiveHelper("scripts/login_session.py", [
    "--session", sessionBase,
    "--method", options.method,
  ]);

  const sessionFile = `${sessionBase}.session`;
  if (existsSync(sessionFile)) {
    chmodSync(sessionFile, 0o600);
  }
}

function parseAuthLoginOptions(args: string[], usage: () => never): AuthLoginOptions {
  let sessionName = "default";
  let method: "qr" | "phone" = "qr";

  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    switch (arg) {
      case "--session":
        sessionName = readValue(args, index, usage);
        index += 1;
        break;
      case "--phone":
        method = "phone";
        break;
      case "--qr":
        method = "qr";
        break;
      default:
        usage();
    }
  }

  return {
    sessionName: sanitizeName(sessionName, "session name"),
    method,
  };
}

function readValue(args: string[], index: number, usage: () => never): string {
  const value = args[index + 1];
  if (!value || value.startsWith("--")) {
    usage();
  }
  return value;
}
