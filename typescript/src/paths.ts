// Minimal JSONPath-like traversal, mirroring python/src/agentreplay/paths.py.

type Token =
  | { kind: "key"; value: string }
  | { kind: "index"; value: number }
  | { kind: "wildcard" };

const TOKEN_RE = /([^.\[\]]+)|\[([0-9]+|\*)\]/g;

function tokenize(path: string): Token[] {
  let p = path;
  if (p.startsWith("$")) {
    p = p.slice(1);
    if (p.startsWith(".")) p = p.slice(1);
  }
  const tokens: Token[] = [];
  let pos = 0;
  while (pos < p.length) {
    if (p[pos] === ".") {
      pos++;
      continue;
    }
    TOKEN_RE.lastIndex = pos;
    const m = TOKEN_RE.exec(p);
    if (!m || m.index !== pos) {
      throw new Error(`invalid path token near "${p.slice(pos, pos + 10)}" in ${path}`);
    }
    if (m[1] !== undefined) tokens.push({ kind: "key", value: m[1] });
    else if (m[2] === "*") tokens.push({ kind: "wildcard" });
    else tokens.push({ kind: "index", value: parseInt(m[2]!, 10) });
    pos = TOKEN_RE.lastIndex;
  }
  return tokens;
}

export type Container = Record<string, unknown> | unknown[];
export type Hit = { container: Container; key: string | number };

export function* iterTargets(root: unknown, path: string): Iterable<Hit> {
  const tokens = tokenize(path);
  yield* walk(root, tokens, 0);
}

function* walk(node: unknown, tokens: Token[], i: number): Iterable<Hit> {
  if (i >= tokens.length) return;
  const tok = tokens[i];
  const last = i === tokens.length - 1;

  if (tok.kind === "key") {
    if (node === null || typeof node !== "object" || Array.isArray(node)) return;
    const obj = node as Record<string, unknown>;
    if (!(tok.value in obj)) return;
    if (last) yield { container: obj, key: tok.value };
    else yield* walk(obj[tok.value], tokens, i + 1);
  } else if (tok.kind === "index") {
    if (!Array.isArray(node)) return;
    if (tok.value >= node.length) return;
    if (last) yield { container: node, key: tok.value };
    else yield* walk(node[tok.value], tokens, i + 1);
  } else {
    if (Array.isArray(node)) {
      for (let idx = 0; idx < node.length; idx++) {
        if (last) yield { container: node, key: idx };
        else yield* walk(node[idx], tokens, i + 1);
      }
    } else if (node !== null && typeof node === "object") {
      const obj = node as Record<string, unknown>;
      for (const k of Object.keys(obj)) {
        if (last) yield { container: obj, key: k };
        else yield* walk(obj[k], tokens, i + 1);
      }
    }
  }
}

export function deleteAt(container: Container, key: string | number): void {
  if (Array.isArray(container)) {
    // Sentinel-fill for arrays to preserve length (mirrors Python).
    (container as unknown[])[key as number] = "<NORMALIZED>";
  } else {
    delete (container as Record<string, unknown>)[key as string];
  }
}
