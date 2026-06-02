import { chmodSync, cpSync, existsSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { rootDir, expandHome } from "../paths.ts";
import { runJsonHelper } from "../python.ts";
import { sessionMetadataPath } from "../sessions.ts";

type ImportResult = {
  id: number;
  username: string | null;
  first_name: string | null;
  last_name: string | null;
  phone_present: boolean;
  session: string;
  telegram_desktop: {
    download_directory: {
      path: string | null;
      source: string;
      available: boolean;
    };
    settings: {
      download_path: string | null;
      ask_download_path: boolean | null;
      error: string | null;
    };
  };
};

type AuthImportOptions = {
  tdata: string;
  sessionName: string;
  passcode: string | undefined;
  password: string | undefined;
  keepSnapshot: boolean;
};

const defaultTdata = "~/snap/telegram-desktop/current/.local/share/TelegramDesktop/tdata";

export function runAuthBootstrap(args: string[], usage: () => never): void {
  const options = parseAuthImportOptions(args, usage);

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

    const parsed = runJsonHelper<ImportResult>("scripts/import_tdesktop_session.py", [
      "--tdata", snapshot,
      "--session", sessionBase,
      ...(options.passcode ? ["--passcode", options.passcode] : []),
      ...(options.password ? ["--password", options.password] : []),
    ]);

    chmodSync(parsed.session, 0o600);
    writeSessionMetadata(options.sessionName, parsed);
    printImportResult(parsed);
    if (options.keepSnapshot) {
      console.log(`snapshot: ${snapshot}`);
    }
  } finally {
    if (!options.keepSnapshot) {
      rmSync(snapshot, { recursive: true, force: true });
    }
  }
}

function parseAuthImportOptions(args: string[], usage: () => never): AuthImportOptions {
  let tdata = defaultTdata;
  let sessionName = "default";
  let passcode: string | undefined;
  let password: string | undefined;
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
      case "--password":
        password = readValue(args, index, usage);
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
    password,
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

function printImportResult(result: ImportResult): void {
  const name = [result.first_name, result.last_name].filter(Boolean).join(" ");
  const username = result.username ? ` @${result.username}` : "";
  console.log(`logged in as ${name || "(unnamed)"}${username} user_id=${result.id}`);
  console.log(`bootstrapped session: ${result.session}`);
  if (result.telegram_desktop.download_directory.path) {
    console.log(`downloads: ${result.telegram_desktop.download_directory.path} (${result.telegram_desktop.download_directory.source})`);
  }
  console.log(`phone_present: ${result.phone_present}`);
}

function writeSessionMetadata(sessionName: string, result: ImportResult): void {
  const path = sessionMetadataPath(sessionName);
  writeFileSync(path, JSON.stringify({
    telegram_desktop: result.telegram_desktop,
  }, null, 2));
  chmodSync(path, 0o600);
}
