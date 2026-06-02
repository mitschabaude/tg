#!/usr/bin/env tsx
import { spawnSync } from "node:child_process";
import { chmodSync, cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

type ProbeResult = {
  id: number;
  username: string | null;
  first_name: string | null;
  last_name: string | null;
  phone_present: boolean;
  session: string;
};

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");

function usage(): never {
  console.error(`Usage:
  tg auth probe [--tdata PATH] [--session NAME] [--passcode PASSCODE] [--keep-snapshot]

Default tdata path:
  ~/snap/telegram-desktop/current/.local/share/TelegramDesktop/tdata`);
  process.exit(2);
}

function readOption(args: string[], name: string): string | undefined {
  const index = args.indexOf(name);
  if (index < 0) {
    return undefined;
  }
  const value = args[index + 1];
  if (!value || value.startsWith("--")) {
    usage();
  }
  return value;
}

function hasFlag(args: string[], name: string): boolean {
  return args.includes(name);
}

function expandHome(path: string): string {
  return path === "~"
    ? homedir()
    : path.startsWith("~/")
      ? join(homedir(), path.slice(2))
      : path;
}

function ensureReadableTdata(path: string): void {
  if (!existsSync(path)) {
    console.error(`tdata path does not exist: ${path}`);
    process.exit(1);
  }
  if (!existsSync(join(path, "key_datas"))) {
    console.error(`not a Telegram Desktop tdata directory: ${path}`);
    process.exit(1);
  }
}

function authProbe(args: string[]): void {
  const defaultTdata = "~/snap/telegram-desktop/current/.local/share/TelegramDesktop/tdata";
  const tdata = resolve(expandHome(readOption(args, "--tdata") ?? defaultTdata));
  const sessionName = readOption(args, "--session") ?? "probe";
  const passcode = readOption(args, "--passcode");
  const keepSnapshot = hasFlag(args, "--keep-snapshot");

  ensureReadableTdata(tdata);

  const snapshot = join(root, "tmp", `tdata-${Date.now()}`);
  const session = join(root, "data", "sessions", sessionName);
  mkdirSync(dirname(snapshot), { recursive: true });
  mkdirSync(dirname(session), { recursive: true });

  cpSync(tdata, snapshot, {
    recursive: true,
    dereference: false,
    errorOnExist: false,
  });

  const python = join(root, ".venv", "bin", "python");
  const helper = join(root, "scripts", "auth_probe.py");
  if (!existsSync(python)) {
    console.error("missing .venv; run: python3 -m venv .venv && .venv/bin/pip install opentele");
    process.exit(1);
  }

  const result = spawnSync(python, [
    helper,
    "--tdata", snapshot,
    "--session", session,
    ...(passcode ? ["--passcode", passcode] : []),
  ], {
    cwd: root,
    encoding: "utf8",
  });

  if (!keepSnapshot) {
    rmSync(snapshot, { recursive: true, force: true });
  }

  if (result.status !== 0) {
    if (result.stdout.trim()) {
      console.error(result.stdout.trim());
    }
    if (result.stderr.trim()) {
      console.error(result.stderr.trim());
    }
    process.exit(result.status ?? 1);
  }

  const parsed = JSON.parse(result.stdout) as ProbeResult;
  chmodSync(parsed.session, 0o600);
  const name = [parsed.first_name, parsed.last_name].filter(Boolean).join(" ");
  const username = parsed.username ? ` @${parsed.username}` : "";
  console.log(`logged in as ${name || "(unnamed)"}${username} user_id=${parsed.id}`);
  console.log(`session: ${parsed.session}`);
  console.log(`phone_present: ${parsed.phone_present}`);
  if (keepSnapshot) {
    console.log(`snapshot: ${snapshot}`);
  }
}

const args = process.argv.slice(2);
if (args[0] === "auth" && args[1] === "probe") {
  authProbe(args.slice(2));
} else {
  usage();
}
