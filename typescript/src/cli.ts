#!/usr/bin/env node

import * as fs from "node:fs";
import { fingerprint } from "./fingerprint.js";
import { applyRedaction } from "./redaction.js";
import type { CassetteHeader, Interaction } from "./cassette.js";

function readCassette(p: string): { header: CassetteHeader; interactions: Interaction[] } {
  const text = fs.readFileSync(p, "utf-8");
  const lines = text.split("\n").filter((l) => l.trim().length > 0);
  if (lines.length === 0) throw new Error(`empty cassette: ${p}`);
  const header = JSON.parse(lines[0]) as CassetteHeader;
  if (header.kind !== "header") throw new Error("first line is not a header");
  const interactions = lines.slice(1).map((l) => JSON.parse(l) as Interaction);
  return { header, interactions };
}

function summary(obj: unknown, limit = 80): string {
  const s = JSON.stringify(obj);
  return s.length > limit ? s.slice(0, limit - 3) + "..." : s;
}

function inspect(p: string): number {
  const { header, interactions } = readCassette(p);
  console.log(`cassette : ${p}`);
  console.log(`format   : v${header.format_version}  library=${header.library}@${header.library_version}`);
  console.log(`created  : ${header.created_at}`);
  console.log(`presets  : ${JSON.stringify(header.normalization.presets || [])}`);
  console.log(`ignore   : ${JSON.stringify(header.normalization.ignore_paths || [])}`);
  console.log(`redact   : ${(header.redaction_rules || []).length} rule(s)`);
  console.log(`interact : ${interactions.length}`);
  console.log();
  for (const it of interactions) {
    console.log(
      `  seq=${String(it.seq).padStart(3)}  ${it.method} ${it.host}${it.path}  ` +
        `[${it.provider}] status=${it.response.status}  req=${summary(it.request.body)}`
    );
  }
  return 0;
}

function show(p: string, seq: number): number {
  const { interactions } = readCassette(p);
  const it = interactions.find((x) => x.seq === seq);
  if (!it) {
    console.error(`error: no interaction with seq=${seq}`);
    return 2;
  }
  console.log(JSON.stringify(it, null, 2));
  return 0;
}

function verify(p: string): number {
  const { header, interactions } = readCassette(p);
  const errors: string[] = [];
  const seen = new Set<number>();
  for (const it of interactions) {
    if (seen.has(it.seq)) errors.push(`duplicate seq=${it.seq}`);
    seen.add(it.seq);
    const redacted = applyRedaction(it.request.body, header.redaction_rules || []);
    const fpExact = fingerprint(it.method, it.host, it.path, redacted);
    const fpNorm = fingerprint(it.method, it.host, it.path, redacted, {
      ignorePaths: header.normalization.ignore_paths,
      presets: header.normalization.presets,
    });
    if (fpExact !== it.request.fp_exact)
      errors.push(`seq=${it.seq}: fp_exact mismatch (stored=${it.request.fp_exact} recomputed=${fpExact})`);
    if (fpNorm !== it.request.fp_norm)
      errors.push(`seq=${it.seq}: fp_norm mismatch (stored=${it.request.fp_norm} recomputed=${fpNorm})`);
  }
  if (errors.length > 0) {
    for (const e of errors) console.error(e);
    console.error(`\nverify: ${errors.length} error(s)`);
    return 1;
  }
  console.log(
    `verify: OK (${interactions.length} interactions, ${(header.redaction_rules || []).length} redaction rules)`
  );
  return 0;
}

function main(argv: string[]): number {
  const [cmd, ...rest] = argv;
  if (!cmd || cmd === "-h" || cmd === "--help") {
    console.log(`Usage: agentreplay <inspect|show|verify> <cassette> [args]`);
    return cmd ? 0 : 2;
  }
  try {
    if (cmd === "inspect") return inspect(rest[0]);
    if (cmd === "show") return show(rest[0], parseInt(rest[1], 10));
    if (cmd === "verify") return verify(rest[0]);
  } catch (e) {
    console.error(`error: ${(e as Error).message}`);
    return 1;
  }
  console.error(`unknown command: ${cmd}`);
  return 2;
}

process.exit(main(process.argv.slice(2)));
