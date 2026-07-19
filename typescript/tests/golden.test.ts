import { describe, it, expect } from "vitest";
import * as fs from "node:fs";
import * as path from "node:path";
import { fingerprint } from "../src/fingerprint.js";
import { applyRedaction } from "../src/redaction.js";
import { Cassette } from "../src/cassette.js";
import { buildFetch } from "../src/fetch.js";

const GOLDEN = path.resolve(__dirname, "../../goldens/cross_language_basic.jsonl");

describe("cross-language golden cassette", () => {
  it("verifies fingerprints computed by Python", () => {
    const text = fs.readFileSync(GOLDEN, "utf-8");
    const lines = text.split("\n").filter((l) => l.trim());
    const header = JSON.parse(lines[0]);
    expect(header.kind).toBe("header");
    for (let i = 1; i < lines.length; i++) {
      const it = JSON.parse(lines[i]);
      const redacted = applyRedaction(it.request.body, header.redaction_rules || []);
      const exact = fingerprint(it.method, it.host, it.path, redacted);
      const norm = fingerprint(it.method, it.host, it.path, redacted, {
        ignorePaths: header.normalization.ignore_paths,
        presets: header.normalization.presets,
      });
      expect(exact).toBe(it.request.fp_exact);
      expect(norm).toBe(it.request.fp_norm);
    }
  });

  it("replays the Python-generated cassette", async () => {
    const c = new Cassette(GOLDEN, { mode: "replay" });
    c.open();
    const w = buildFetch(c, async () => {
      throw new Error("network in replay!");
    });
    const r = await w("https://api.anthropic.com/v1/messages", {
      method: "POST",
      body: JSON.stringify({
        model: "claude-3",
        messages: [{ role: "user", content: "hi" }],
        // uuid preset lets a *different* uuid still match fp_norm
        trace_id: "abcdef12-3456-4abc-8def-abcdef123456",
      }),
    });
    const body = await r.json();
    expect(body.id).toBe("msg_g1");
    c.close();
  });
});
