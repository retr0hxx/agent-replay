import { describe, it, expect } from "vitest";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { Cassette } from "../src/cassette.js";
import { buildFetch, installGlobalFetch, restoreGlobalFetch } from "../src/fetch.js";
import { CassetteMissError, NonTargetHostError } from "../src/errors.js";

function tmpFile(name: string): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "agent-replay-"));
  return path.join(dir, name);
}

function fakeUpstream(responses: { status?: number; body: unknown }[]) {
  const queue = [...responses];
  return async function (_input: RequestInfo | URL, _init?: RequestInit): Promise<Response> {
    const r = queue.shift();
    if (!r) throw new Error("fake upstream exhausted");
    return new Response(JSON.stringify(r.body), {
      status: r.status ?? 200,
      headers: { "content-type": "application/json" },
    });
  };
}

describe("record → replay roundtrip", () => {
  it("captures & re-serves interactions", async () => {
    const cassettePath = tmpFile("session.jsonl");

    // record
    {
      const c = new Cassette(cassettePath, { mode: "record" });
      c.open();
      const wrapped = buildFetch(
        c,
        fakeUpstream([
          { body: { id: "msg_1", content: [{ type: "text", text: "hi" }] } },
          { body: { id: "msg_2", content: [{ type: "text", text: "bye" }] } },
        ])
      );
      const r1 = await wrapped("https://api.anthropic.com/v1/messages", {
        method: "POST",
        body: JSON.stringify({ model: "m", messages: [{ role: "user", content: "yo" }] }),
      });
      const r2 = await wrapped("https://api.anthropic.com/v1/messages", {
        method: "POST",
        body: JSON.stringify({ model: "m", messages: [{ role: "user", content: "ok" }] }),
      });
      expect((await r1.json()).id).toBe("msg_1");
      expect((await r2.json()).id).toBe("msg_2");
      c.close();
    }

    const lines = fs.readFileSync(cassettePath, "utf-8").trim().split("\n");
    expect(JSON.parse(lines[0]).kind).toBe("header");
    expect(lines.length).toBe(3);

    // replay
    {
      const c = new Cassette(cassettePath, { mode: "replay" });
      c.open();
      const wrapped = buildFetch(c, async () => {
        throw new Error("network in replay!");
      });
      const r1 = await wrapped("https://api.anthropic.com/v1/messages", {
        method: "POST",
        body: JSON.stringify({ model: "m", messages: [{ role: "user", content: "yo" }] }),
      });
      const r2 = await wrapped("https://api.anthropic.com/v1/messages", {
        method: "POST",
        body: JSON.stringify({ model: "m", messages: [{ role: "user", content: "ok" }] }),
      });
      expect((await r1.json()).id).toBe("msg_1");
      expect((await r2.json()).id).toBe("msg_2");
      c.close();
    }
  });

  it("throws on unmatched request when onMiss=error", async () => {
    const cassettePath = tmpFile("miss.jsonl");
    const c = new Cassette(cassettePath, { mode: "record" });
    c.open();
    const wrapped = buildFetch(c, fakeUpstream([{ body: { ok: true } }]));
    await wrapped("https://api.anthropic.com/v1/messages", {
      method: "POST",
      body: JSON.stringify({ model: "m", messages: [] }),
    });
    c.close();

    const c2 = new Cassette(cassettePath, { mode: "replay" });
    c2.open();
    const w2 = buildFetch(c2, async () => new Response("no", { status: 200 }));
    await w2("https://api.anthropic.com/v1/messages", {
      method: "POST",
      body: JSON.stringify({ model: "m", messages: [] }),
    });
    await expect(
      w2("https://api.anthropic.com/v1/messages", {
        method: "POST",
        body: JSON.stringify({ model: "m", messages: [{ role: "u", content: "diff" }] }),
      })
    ).rejects.toBeInstanceOf(CassetteMissError);
    c2.close();
  });

  it("blocks non-target hosts", async () => {
    const cassettePath = tmpFile("nt.jsonl");
    const c = new Cassette(cassettePath, { mode: "record" });
    c.open();
    const w = buildFetch(c, fakeUpstream([{ body: { ok: true } }]));
    await w("https://api.anthropic.com/v1/messages", { method: "POST", body: "{}" });
    c.close();

    const c2 = new Cassette(cassettePath, { mode: "replay" });
    c2.open();
    const w2 = buildFetch(c2, async () => new Response("!", { status: 200 }));
    await expect(w2("https://example.com/foo")).rejects.toBeInstanceOf(NonTargetHostError);
    c2.close();
  });

  it("uses preset to recover from timestamp drift", async () => {
    const cassettePath = tmpFile("norm.jsonl");
    const c = new Cassette(cassettePath, {
      mode: "record",
      presets: ["timestamps"],
    });
    c.open();
    const w = buildFetch(c, fakeUpstream([{ body: { ok: true } }]));
    await w("https://api.anthropic.com/v1/messages", {
      method: "POST",
      body: JSON.stringify({
        model: "m",
        messages: [{ role: "user", content: "hi" }],
        ts: "2026-01-01T00:00:00Z",
      }),
    });
    c.close();

    const c2 = new Cassette(cassettePath, { mode: "replay" });
    c2.open();
    const w2 = buildFetch(c2, async () => new Response("no", { status: 200 }));
    const r = await w2("https://api.anthropic.com/v1/messages", {
      method: "POST",
      body: JSON.stringify({
        model: "m",
        messages: [{ role: "user", content: "hi" }],
        ts: "2026-07-19T00:00:00Z", // different timestamp
      }),
    });
    const body = await r.json();
    expect(body).toEqual({ ok: true });
    expect(c2.report.divergences.filter((d) => d.kind === "request").length).toBe(0);
    c2.close();
  });
});

describe("installGlobalFetch", () => {
  it("swaps and restores globalThis.fetch", async () => {
    const cassettePath = tmpFile("g.jsonl");
    const before = globalThis.fetch;
    const c = new Cassette(cassettePath, { mode: "record" });
    c.open();
    installGlobalFetch(c);
    const during = globalThis.fetch;
    restoreGlobalFetch();
    const after = globalThis.fetch;
    c.close();
    expect(during).not.toBe(before);
    expect(after).toBe(before);
  });
});
