// Canonical JSON (RFC 8785 JCS approximation) — matches Python side for
// the value set used by our target APIs. See implementation-notes §1.1.

export function canonicalJSON(value: unknown): string {
  return stringify(value);
}

function stringify(v: unknown): string {
  if (v === null) return "null";
  if (typeof v === "boolean") return v ? "true" : "false";
  if (typeof v === "number") {
    if (!Number.isFinite(v)) {
      throw new Error("canonicalJSON: non-finite number is not allowed");
    }
    // JCS §3.2.2: use ECMAScript Number.prototype.toString.
    return String(v);
  }
  if (typeof v === "string") return JSON.stringify(v);
  if (Array.isArray(v)) {
    return "[" + v.map((x) => stringify(x)).join(",") + "]";
  }
  if (typeof v === "object") {
    const obj = v as Record<string, unknown>;
    const keys = Object.keys(obj).sort();
    return (
      "{" +
      keys
        .map((k) => JSON.stringify(k) + ":" + stringify(obj[k]))
        .join(",") +
      "}"
    );
  }
  throw new Error(`canonicalJSON: unsupported type ${typeof v}`);
}
