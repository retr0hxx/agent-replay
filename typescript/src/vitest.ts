// vitest / any test-runner helper: withCassette(name, opts?, fn)

import * as path from "node:path";
import { Cassette, CassetteOptions } from "./cassette.js";
import { installGlobalFetch, restoreGlobalFetch } from "./fetch.js";

export interface WithCassetteOptions extends CassetteOptions {
  dir?: string;
}

export async function withCassette<T>(
  name: string,
  optsOrFn: WithCassetteOptions | ((c: Cassette) => Promise<T> | T),
  maybeFn?: (c: Cassette) => Promise<T> | T
): Promise<T> {
  let opts: WithCassetteOptions;
  let fn: (c: Cassette) => Promise<T> | T;
  if (typeof optsOrFn === "function") {
    opts = {};
    fn = optsOrFn;
  } else {
    opts = optsOrFn;
    fn = maybeFn!;
  }
  const dir = opts.dir || "__cassettes__";
  const filename = name.endsWith(".jsonl") ? name : `${name}.jsonl`;
  const p = path.join(dir, filename);
  const cassette = new Cassette(p, opts);
  cassette.open();
  installGlobalFetch(cassette);
  try {
    return await fn(cassette);
  } finally {
    restoreGlobalFetch();
    cassette.close();
  }
}
