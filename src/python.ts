import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";
import { rootDir } from "./paths.js";

export function runJsonHelper<T>(script: string, args: string[]): T {
  const python = join(rootDir, ".venv", "bin", "python");
  if (!existsSync(python)) {
    console.error("missing .venv; run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt");
    process.exit(1);
  }

  const result = spawnSync(python, [join(rootDir, script), ...args], {
    cwd: rootDir,
    encoding: "utf8",
  });

  if (result.status !== 0) {
    printHelperOutput(result.stdout, result.stderr);
    process.exit(result.status ?? 1);
  }

  try {
    return JSON.parse(result.stdout) as T;
  } catch {
    printHelperOutput(result.stdout, result.stderr);
    console.error("helper did not return valid JSON");
    process.exit(1);
  }
}

function printHelperOutput(stdout: string, stderr: string): void {
  if (stdout.trim()) {
    console.error(stdout.trim());
  }
  if (stderr.trim()) {
    console.error(stderr.trim());
  }
}
