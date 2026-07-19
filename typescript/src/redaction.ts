// Redaction + auth header stripping (mirrors Python).

import { iterTargets } from "./paths.js";

const AUTH_HEADERS = new Set([
  "authorization",
  "x-api-key",
  "openai-organization",
  "openai-project",
  "anthropic-version",
  "anthropic-beta",
  "cookie",
  "set-cookie",
  "proxy-authorization",
]);

export function stripAuthHeaders(headers: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(headers)) {
    if (!AUTH_HEADERS.has(k.toLowerCase())) out[k] = v;
  }
  return out;
}

export type RedactRule = { path: string; replace?: unknown };

export function applyRedaction(body: unknown, rules: RedactRule[]): unknown {
  if (!rules || rules.length === 0) return body;
  const out = deepClone(body);
  for (const rule of rules) {
    const replacement = rule.replace !== undefined ? rule.replace : "***";
    for (const { container, key } of iterTargets(out, rule.path)) {
      (container as Record<string | number, unknown>)[key as string] = replacement;
    }
  }
  return out;
}

function deepClone<T>(v: T): T {
  if (v === null || typeof v !== "object") return v;
  return JSON.parse(JSON.stringify(v));
}
