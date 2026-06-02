import { chmodSync, cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { rootDir, expandHome } from "../paths.js";
import { runJsonHelper } from "../python.js";

type ProbeResult = {
  id: number;
  username: string | null;
  first_name: string | null;
  last_name: string | null;
  phone_present: boolean;
  session: string;
};

type AuthProbeOptions = {
  tdata: string;
  sessionName: string;
  passcode: string | undefined;
  keepSnapshot: boolean;
};

const defaultTdata = "~/snap/telegram-desktop/current/.local/share/TelegramDesktop/tdata";

export function runAuthProbe(args: string[], usage: () => never): void {
  const options = parseAuthProbeOptions(args, usage);

  ensureReadableTdata(options.tdata);

  const snapshot = join(rootDir, "tmp", `tdata-${Date.now()}`);
  const sessionBase = join(rootDir, "data", "sessions", options.sessionName);
  ensurePrivateDir(dirname(snapshot));
  ensurePrivateDir(dirname(sessionBase));

  try {
    cpSync(options.tdata, snapshot, {
      recursive: true,
      dereference: false,
      errorOnExist: false,
    });

    const parsed = runJsonHelper<ProbeResult>("scripts/auth_probe.py", [
      "--tdata", snapshot,
      "--session", sessionBase,
      ...(options.passcode ? ["--passcode", options.passcode] : []),
    ]);

    chmodSync(parsed.session, 0o600);
    printProbeResult(parsed);
    if (options.keepSnapshot) {
      console.log(`snapshot: ${snapshot}`);
    }
  } finally {
    if (!options.keepSnapshot) {
      rmSync(snapshot, { recursive: true, force: true });
    }
  }
}

function parseAuthProbeOptions(args: string[], usage: () => never): AuthProbeOptions {
  let tdata = defaultTdata;
  let sessionName = "probe";
  let passcode: string | undefined;
  let keepSnapshot = false;

  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    switch (arg) {
      case "--tdata":
        tdata = readValue(args, index, usage);
        index += 1;
        break;
      case "--session":
        sessionName = readValue(args, index, usage);
        index += 1;
        break;
      case "--passcode":
        passcode = readValue(args, index, usage);
        index += 1;
        break;
      case "--keep-snapshot":
        keepSnapshot = true;
        break;
      default:
        usage();
    }
  }

  return {
    tdata: resolve(expandHome(tdata)),
    sessionName: sanitizeSessionName(sessionName),
    passcode,
    keepSnapshot,
  };
}

function readValue(args: string[], index: number, usage: () => never): string {
  const value = args[index + 1];
  if (!value || value.startsWith("--")) {
    usage();
  }
  return value;
}

function sanitizeSessionName(name: string): string {
  if (!/^[a-zA-Z0-9._-]+$/.test(name)) {
    console.error("session name may only contain letters, numbers, dot, underscore, and dash");
    process.exit(2);
  }
  return name;
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

function ensurePrivateDir(path: string): void {
  mkdirSync(path, { recursive: true, mode: 0o700 });
  chmodSync(path, 0o700);
}

function printProbeResult(result: ProbeResult): void {
  const name = [result.first_name, result.last_name].filter(Boolean).join(" ");
  const username = result.username ? ` @${result.username}` : "";
  console.log(`logged in as ${name || "(unnamed)"}${username} user_id=${result.id}`);
  console.log(`session: ${result.session}`);
  console.log(`phone_present: ${result.phone_present}`);
}
