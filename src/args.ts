export function readOption(args: string[], index: number, usage: () => never): string {
  const value = args[index + 1];
  if (!value || value.startsWith("--")) {
    usage();
  }
  return value;
}

export function parseLimit(value: string, usage: () => never): number {
  const result = Number(value);
  if (!Number.isInteger(result) || result < 1 || result > 500) {
    usage();
  }
  return result;
}

export function parseOffset(value: string, usage: () => never): number {
  const result = Number(value);
  if (!Number.isInteger(result) || result < 0 || result > 100000) {
    usage();
  }
  return result;
}

export function sanitizeName(name: string, label: string): string {
  if (!/^[a-zA-Z0-9._-]+$/.test(name)) {
    console.error(`${label} may only contain letters, numbers, dot, underscore, and dash`);
    process.exit(2);
  }
  return name;
}
