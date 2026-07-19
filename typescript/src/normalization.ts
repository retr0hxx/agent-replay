// Normalization: ignore_paths + built-in presets. Mirrors Python.

import { iterTargets } from "./paths.js";

const ISO8601 =
  /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?$/;
const UUID_RE =
  /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$/;
const REQ_ID_RE = /^(?:req|msg|resp)_[A-Za-z0-9]{16,}$/;
const EPOCH_MIN = 1_000_000_000;
const EPOCH_MAX = 9_999_999_999;
const NORMALIZED = "<NORMALIZED>";

function matchesPreset(value: unknown, presets: Set<string>): boolean {
  if (typeof value === "string") {
    if (presets.has("timestamps") && ISO8601.test(value)) return true;
    if (presets.has("uuids") && UUID_RE.test(value)) return true;
    if (presets.has("request_ids") && REQ_ID_RE.test(value)) return true;
  }
  if (typeof value === "number" && Number.isInteger(value)) {
    if (presets.has("timestamps") && value >= EPOCH_MIN && value <= EPOCH_MAX) return true;
  }
  return false;
}

function applyPresets(node: unknown, presets: Set<string>): unknown {
  if (Array.isArray(node)) return node.map((v) => applyPresets(v, presets));
  if (node !== null && typeof node === "object") {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(node as Record<string, unknown>)) {
      out[k] = applyPresets(v, presets);
    }
    return out;
  }
  return matchesPreset(node, presets) ? NORMALIZED : node;
}

export function normalize(
  body: unknown,
  opts: { ignorePaths?: string[]; presets?: string[] } = {}
): unknown {
  const { ignorePaths, presets } = opts;
  if ((!ignorePaths || ignorePaths.length === 0) && (!presets || presets.length === 0)) {
    return body;
  }
  let out = deepClone(body);
  if (presets && presets.length > 0) {
    out = applyPresets(out, new Set(presets));
  }
  if (ignorePaths && ignorePaths.length > 0) {
    for (const path of ignorePaths) {
      for (const { container, key } of Array.from(iterTargets(out, path))) {
        if (Array.isArray(container)) {
          (container as unknown[])[key as number] = NORMALIZED;
        } else {
          delete (container as Record<string, unknown>)[key as string];
        }
      }
    }
  }
  return out;
}

function deepClone<T>(v: T): T {
  if (v === null || typeof v !== "object") return v;
  return JSON.parse(JSON.stringify(v));
}
