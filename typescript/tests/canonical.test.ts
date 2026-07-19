import { describe, it, expect } from "vitest";
import { canonicalJSON } from "../src/canonical.js";
import { fingerprint } from "../src/fingerprint.js";

describe("canonicalJSON", () => {
  it("key-sorts and drops whitespace", () => {
    expect(canonicalJSON({ b: 2, a: [3, { z: 1, y: 2 }] })).toBe(
      '{"a":[3,{"y":2,"z":1}],"b":2}'
    );
  });

  it("emits unicode verbatim", () => {
    expect(canonicalJSON({ k: "日本語" })).toBe('{"k":"日本語"}');
  });
});

describe("fingerprint", () => {
  it("is order-insensitive", () => {
    const a = fingerprint("POST", "api.anthropic.com", "/v1/messages", {
      model: "m",
      messages: [],
    });
    const b = fingerprint("post", "API.Anthropic.com", "/v1/messages", {
      messages: [],
      model: "m",
    });
    expect(a).toBe(b);
    expect(a.startsWith("sha256:")).toBe(true);
  });

  it("presets shift fp_norm", () => {
    const body = { id: "12345678-1234-4abc-8def-1234567890ab", hello: "world" };
    const exact = fingerprint("POST", "h", "/p", body);
    const norm = fingerprint("POST", "h", "/p", body, { presets: ["uuids"] });
    expect(exact).not.toBe(norm);
  });
});
