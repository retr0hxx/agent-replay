// fetch() replacement wired to a Cassette.

import { Cassette } from "./cassette.js";
import {
  CassetteMissError,
  NonTargetHostError,
} from "./errors.js";
import {
  detect,
  parseSSEEvents,
  reassemble,
  TARGET_HOSTS,
} from "./providers.js";
import { stripAuthHeaders } from "./redaction.js";

const AUTO_TEXT_TYPES = ["application/json", "text/"];

async function readBody(req: Request): Promise<{ raw: string; parsed: unknown }> {
  try {
    const text = await req.clone().text();
    if (!text) return { raw: "", parsed: null };
    try {
      return { raw: text, parsed: JSON.parse(text) };
    } catch {
      return { raw: text, parsed: { __non_json_text__: text } };
    }
  } catch {
    return { raw: "", parsed: null };
  }
}

function isTarget(host: string, urlPath: string): boolean {
  if (TARGET_HOSTS.has(host.toLowerCase())) return true;
  return detect(host, urlPath) !== "generic";
}

function headersToObject(headers: Headers | Record<string, string>): Record<string, string> {
  if (headers instanceof Headers) {
    const out: Record<string, string> = {};
    headers.forEach((v, k) => (out[k] = v));
    return out;
  }
  return { ...headers };
}

function isSSEContentType(headers: Headers): boolean {
  const ct = headers.get("content-type") || "";
  return ct.toLowerCase().includes("text/event-stream");
}

function serializeBody(body: unknown): { text: string; contentType: string } {
  if (body === null || body === undefined) return { text: "", contentType: "" };
  if (typeof body === "object" && body !== null && "__non_json_text__" in (body as any)) {
    return { text: String((body as any).__non_json_text__), contentType: "text/plain" };
  }
  return { text: JSON.stringify(body), contentType: "application/json" };
}

export function buildFetch(cassette: Cassette, upstream: typeof fetch): typeof fetch {
  return async function agentReplayFetch(
    input: RequestInfo | URL,
    init?: RequestInit
  ): Promise<Response> {
    const request = new Request(input, init);
    const url = new URL(request.url);
    const host = url.host;
    const urlPath = url.pathname;
    const method = request.method.toUpperCase();

    const { parsed: body } = await readBody(request);
    const mode = cassette.effectiveMode;
    const target = isTarget(host, urlPath);
    const allowed = cassette.allowPassthroughHosts.has(host.toLowerCase());

    if (mode === "passthrough") return upstream(request);
    if (!target) {
      if (allowed) return upstream(request);
      throw new NonTargetHostError(
        `request to non-target host "${host}" blocked; add to allowPassthroughHosts to permit`
      );
    }

    if (mode === "replay") {
      const inter = cassette.lookup(method, host, urlPath, body);
      if (inter === null) return onMiss();
      return buildReplayResponse(inter, cassette.streamTiming);
    }

    if (mode === "record") {
      return recordResponse();
    }

    throw new Error(`unknown mode: ${mode}`);

    async function onMiss(): Promise<Response> {
      cassette.report.add({
        kind: "flow_over",
        detail: `no cassette entry for ${method} ${host}${urlPath}`,
      });
      if (cassette.onMiss === "error") {
        throw new CassetteMissError(
          `no matching interaction for ${method} ${host}${urlPath} (onMiss='error')`
        );
      }
      if (cassette.onMiss === "passthrough") return upstream(request);
      return recordResponse();
    }

    async function recordResponse(): Promise<Response> {
      const startedAt = new Date().toISOString();
      const t0 = Date.now();
      const upstreamResp = await upstream(request);
      const reqHeaders = cassette.includeHeaders.size > 0
        ? filterHeaders(headersToObject(request.headers))
        : undefined;
      const respHeaders = cassette.includeHeaders.size > 0
        ? filterHeaders(headersToObject(upstreamResp.headers))
        : undefined;

      if (isSSEContentType(upstreamResp.headers)) {
        const rawText = await upstreamResp.clone().text();
        const events = parseSSEEvents(rawText);
        const latencyMs = Date.now() - t0;
        const per = events.length > 0 ? Math.floor(latencyMs / events.length) : 0;
        const streamRecords = events.map((ev, i) => ({
          delay_ms: i === 0 ? 0 : per,
          data: ev.raw,
        }));
        const provider = detect(host, urlPath);
        const finalBody = reassemble(provider, events);
        cassette.record({
          method,
          host,
          path: urlPath,
          requestBody: body,
          responseStatus: upstreamResp.status,
          responseBody: finalBody,
          responseStream: streamRecords,
          requestHeaders: reqHeaders,
          responseHeaders: respHeaders,
          startedAt,
          latencyMs,
        });
        // Return a fresh Response with the same content so caller can read it.
        return new Response(rawText, {
          status: upstreamResp.status,
          headers: upstreamResp.headers,
        });
      }

      const text = await upstreamResp.clone().text();
      const latencyMs = Date.now() - t0;
      let parsed: unknown = null;
      if (text) {
        try {
          parsed = JSON.parse(text);
        } catch {
          parsed = { __non_json_text__: text };
        }
      }
      cassette.record({
        method,
        host,
        path: urlPath,
        requestBody: body,
        responseStatus: upstreamResp.status,
        responseBody: parsed,
        responseStream: null,
        requestHeaders: reqHeaders,
        responseHeaders: respHeaders,
        startedAt,
        latencyMs,
      });
      return new Response(text, {
        status: upstreamResp.status,
        headers: upstreamResp.headers,
      });
    }

    function filterHeaders(headers: Record<string, string>): Record<string, string> {
      const stripped = stripAuthHeaders(headers);
      const out: Record<string, string> = {};
      for (const [k, v] of Object.entries(stripped)) {
        if (cassette.includeHeaders.has(k.toLowerCase())) out[k] = v;
      }
      return out;
    }
  };
}

function buildReplayResponse(inter: { response: { status: number; body: unknown; stream: { delay_ms: number; data: string }[] | null; headers?: Record<string, string> } }, timing: "none" | "recorded"): Response {
  const headers = new Headers(inter.response.headers || {});
  if (inter.response.stream) {
    if (!headers.has("content-type")) headers.set("content-type", "text/event-stream");
    const stream = new ReadableStream<Uint8Array>({
      async start(controller) {
        const enc = new TextEncoder();
        for (const rec of inter.response.stream!) {
          if (timing === "recorded" && rec.delay_ms > 0) {
            await new Promise((r) => setTimeout(r, rec.delay_ms));
          }
          controller.enqueue(enc.encode(rec.data));
        }
        controller.close();
      },
    });
    return new Response(stream, { status: inter.response.status, headers });
  }
  const { text, contentType } = serializeBody(inter.response.body);
  if (contentType && !headers.has("content-type")) headers.set("content-type", contentType);
  return new Response(text || null, { status: inter.response.status, headers });
}

// ---- global fetch monkeypatch --------------------------------------------

let _originalFetch: typeof fetch | null = null;
let _installedCassette: Cassette | null = null;

export function installGlobalFetch(cassette: Cassette): void {
  if (_installedCassette) {
    throw new Error("agent-replay: fetch already installed for another cassette");
  }
  _originalFetch = globalThis.fetch;
  const bound = _originalFetch.bind(globalThis);
  const wrapped = buildFetch(cassette, bound);
  (globalThis as any).fetch = wrapped;
  _installedCassette = cassette;
}

export function restoreGlobalFetch(): void {
  if (_originalFetch !== null) {
    (globalThis as any).fetch = _originalFetch;
    _originalFetch = null;
    _installedCassette = null;
  }
}
