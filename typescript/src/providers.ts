export type Provider = "anthropic" | "openai" | "generic";

const ANTHROPIC_HOSTS = new Set(["api.anthropic.com"]);
const OPENAI_HOSTS = new Set(["api.openai.com"]);

export const TARGET_HOSTS = new Set([...ANTHROPIC_HOSTS, ...OPENAI_HOSTS]);

export function detect(host: string, path: string): Provider {
  const h = host.toLowerCase();
  if (ANTHROPIC_HOSTS.has(h) && path.startsWith("/v1/messages")) return "anthropic";
  if (
    OPENAI_HOSTS.has(h) &&
    (path.startsWith("/v1/chat/completions") || path.startsWith("/v1/responses"))
  ) {
    return "openai";
  }
  return "generic";
}

// ---- SSE parsing --------------------------------------------------------

export type SSEEvent = { raw: string };

export function parseSSEEvents(raw: string): SSEEvent[] {
  const text = raw.replace(/\r\n/g, "\n");
  const events: SSEEvent[] = [];
  let buf: string[] = [];
  for (const line of text.split("\n")) {
    if (line === "") {
      if (buf.length > 0) {
        events.push({ raw: buf.join("\n") + "\n\n" });
        buf = [];
      }
    } else {
      buf.push(line);
    }
  }
  if (buf.length > 0) events.push({ raw: buf.join("\n") + "\n\n" });
  return events;
}

function dataLines(raw: string): string[] {
  return raw
    .split("\n")
    .filter((l) => l.startsWith("data:"))
    .map((l) => (l.startsWith("data: ") ? l.slice(6) : l.slice(5)));
}

function eventNames(raw: string): string[] {
  return raw
    .split("\n")
    .filter((l) => l.startsWith("event:"))
    .map((l) => l.split(":", 2)[1]?.trim() || "");
}

export function reassemble(provider: Provider, events: SSEEvent[]): unknown | null {
  if (provider === "anthropic") return reassembleAnthropic(events);
  if (provider === "openai") return reassembleOpenAI(events);
  return null;
}

function reassembleAnthropic(events: SSEEvent[]): unknown | null {
  let message: Record<string, any> | null = null;
  const blocks: Record<number, Record<string, any>> = {};
  for (const ev of events) {
    const names = eventNames(ev.raw);
    const datas = dataLines(ev.raw);
    for (let i = 0; i < Math.min(names.length, datas.length); i++) {
      const name = names[i];
      const data = datas[i];
      if (!data) continue;
      let obj: any;
      try {
        obj = JSON.parse(data);
      } catch {
        continue;
      }
      if (name === "message_start") {
        message = obj.message || {};
        message!.content = message!.content || [];
      } else if (name === "content_block_start") {
        const idx = obj.index;
        blocks[idx] = { ...obj.content_block };
        if (blocks[idx].type === "text" && blocks[idx].text === undefined) blocks[idx].text = "";
        if (blocks[idx].type === "tool_use" && blocks[idx].input === undefined) blocks[idx].input = "";
      } else if (name === "content_block_delta") {
        const idx = obj.index;
        const delta = obj.delta || {};
        const blk = blocks[idx] || {};
        if (delta.type === "text_delta") blk.text = (blk.text || "") + (delta.text || "");
        if (delta.type === "input_json_delta") blk.input = (blk.input || "") + (delta.partial_json || "");
        blocks[idx] = blk;
      } else if (name === "content_block_stop") {
        const idx = obj.index;
        const blk = blocks[idx];
        if (blk && blk.type === "tool_use" && typeof blk.input === "string") {
          try {
            blk.input = blk.input ? JSON.parse(blk.input) : {};
          } catch {}
        }
      } else if (name === "message_delta") {
        if (message === null) continue;
        Object.assign(message, obj.delta || {});
        if (obj.usage) message.usage = obj.usage;
      }
    }
  }
  if (message === null) return null;
  message.content = Object.keys(blocks)
    .map((k) => parseInt(k, 10))
    .sort((a, b) => a - b)
    .map((k) => blocks[k]);
  return message;
}

function reassembleOpenAI(events: SSEEvent[]): unknown | null {
  let final: any = null;
  const choices: Record<number, any> = {};
  for (const ev of events) {
    for (const data of dataLines(ev.raw)) {
      if (!data || data === "[DONE]") continue;
      let obj: any;
      try {
        obj = JSON.parse(data);
      } catch {
        continue;
      }
      if (final === null) {
        final = {
          id: obj.id,
          object: "chat.completion",
          created: obj.created,
          model: obj.model,
          choices: [],
        };
      }
      for (const ch of obj.choices || []) {
        const idx = ch.index ?? 0;
        const slot = choices[idx] || (choices[idx] = {
          index: idx,
          message: { role: "assistant", content: "" },
          finish_reason: null,
        });
        const delta = ch.delta || {};
        if (delta.role) slot.message.role = delta.role;
        if (delta.content) slot.message.content = (slot.message.content || "") + delta.content;
        if (ch.finish_reason) slot.finish_reason = ch.finish_reason;
      }
      if (obj.usage) final.usage = obj.usage;
    }
  }
  if (final === null) return null;
  final.choices = Object.keys(choices)
    .map((k) => parseInt(k, 10))
    .sort((a, b) => a - b)
    .map((k) => choices[k]);
  return final;
}
