// JSON diff mirroring Python's diff.py.

export type DiffOp = "changed" | "added" | "removed";
export interface DiffRecord {
  path: string;
  op: DiffOp;
  expected?: unknown;
  actual?: unknown;
}

export function jsonDiff(expected: unknown, actual: unknown, path = ""): DiffRecord[] {
  const out: DiffRecord[] = [];
  walk(expected, actual, path, out);
  return out;
}

function walk(expected: unknown, actual: unknown, path: string, out: DiffRecord[]) {
  if (isObject(expected) && isObject(actual)) {
    const keys = new Set([...Object.keys(expected), ...Object.keys(actual)]);
    for (const k of keys) {
      const sub = path ? `${path}.${k}` : k;
      if (!(k in actual)) out.push({ path: sub, op: "removed", expected: expected[k] });
      else if (!(k in expected)) out.push({ path: sub, op: "added", actual: actual[k] });
      else walk(expected[k], actual[k], sub, out);
    }
    return;
  }
  if (Array.isArray(expected) && Array.isArray(actual)) {
    const n = Math.max(expected.length, actual.length);
    for (let i = 0; i < n; i++) {
      const sub = `${path}[${i}]`;
      if (i >= actual.length) out.push({ path: sub, op: "removed", expected: expected[i] });
      else if (i >= expected.length) out.push({ path: sub, op: "added", actual: actual[i] });
      else walk(expected[i], actual[i], sub, out);
    }
    return;
  }
  if (!deepEqual(expected, actual)) {
    out.push({ path: path || "$", op: "changed", expected, actual });
  }
}

function isObject(v: unknown): v is Record<string, unknown> {
  return v !== null && typeof v === "object" && !Array.isArray(v);
}

function deepEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (typeof a !== typeof b) return false;
  if (a === null || b === null) return a === b;
  if (typeof a === "object") return JSON.stringify(a) === JSON.stringify(b);
  return false;
}
