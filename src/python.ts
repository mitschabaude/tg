import { spawnSync } from "node:child_process";
import { join } from "node:path";
import { rootDir } from "./paths.ts";

export function runJsonHelper<T>(script: string, args: string[]): T {
  const result = spawnSync("uv", ["run", "python", join(rootDir, script), ...args], {
    cwd: rootDir,
    encoding: "utf8",
  });

  if (result.error) {
    if (result.error.message.includes("ENOENT")) {
      console.error("missing uv; install uv and run: uv sync");
    } else {
      console.error(result.error.message);
    }
    process.exit(1);
  }

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
