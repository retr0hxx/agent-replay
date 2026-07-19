import { createHash } from "node:crypto";
import { canonicalJSON } from "./canonical.js";
import { normalize } from "./normalization.js";

export function fingerprint(
  method: string,
  host: string,
  path: string,
  body: unknown,
  opts: { ignorePaths?: string[]; presets?: string[] } = {}
): string {
  const normalized = normalize(body, opts);
  const canon = canonicalJSON(normalized);
  const payload = `${method.toUpperCase()}\n${host.toLowerCase()}\n${path}\n${canon}`;
  return "sha256:" + createHash("sha256").update(payload, "utf8").digest("hex");
}
