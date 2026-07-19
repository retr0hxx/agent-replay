import * as fs from "node:fs";
import * as path from "node:path";
import { canonicalJSON } from "./canonical.js";
import { jsonDiff } from "./diff.js";
import { Divergence, Report } from "./divergence.js";
import {
  AgentReplayError,
  CassetteFormatError,
  CassetteMissError,
  DivergenceError,
} from "./errors.js";
import { fingerprint as computeFp } from "./fingerprint.js";
import { detect, Provider } from "./providers.js";
import { applyRedaction, RedactRule } from "./redaction.js";

export const FORMAT_VERSION = 1;
export const LIBRARY_NAME = "agent-replay";
export const LIBRARY_VERSION = "0.1.0";

export type Mode = "record" | "replay" | "auto" | "passthrough";
export type OnMiss = "error" | "passthrough" | "record_new";
export type DivergencePolicy = "error" | "warn" | "silent";
export type StreamTiming = "none" | "recorded";

export interface CassetteOptions {
  mode?: Mode;
  onMiss?: OnMiss;
  divergence?: DivergencePolicy;
  requireAllPlayed?: boolean;
  ignorePaths?: string[];
  presets?: string[];
  redact?: RedactRule[];
  allowPassthroughHosts?: string[];
  streamTiming?: StreamTiming;
  includeHeaders?: string[];
  labels?: Record<string, unknown>;
}

export interface CassetteHeader {
  kind: "header";
  format_version: number;
  library: string;
  library_version: string;
  created_at: string;
  normalization: { ignore_paths: string[]; presets: string[] };
  redaction_rules: RedactRule[];
  labels: Record<string, unknown>;
}

export interface Interaction {
  kind: "interaction";
  id: string;
  seq: number;
  provider: Provider;
  method: string;
  host: string;
  path: string;
  request: {
    body: unknown;
    fp_exact: string;
    fp_norm: string;
    headers?: Record<string, string>;
  };
  response: {
    status: number;
    body: unknown;
    stream: { delay_ms: number; data: string }[] | null;
    headers?: Record<string, string>;
  };
  timing?: { started_at: string | null; latency_ms: number | null };
}

export class Cassette {
  path: string;
  mode: Mode;
  effectiveMode: Mode = "auto";
  onMiss: OnMiss;
  divergencePolicy: DivergencePolicy;
  requireAllPlayed: boolean;
  streamTiming: StreamTiming;
  allowPassthroughHosts: Set<string>;
  includeHeaders: Set<string>;
  labels: Record<string, unknown>;

  ignorePaths: string[];
  presets: string[];
  redact: RedactRule[];

  header: CassetteHeader | null = null;
  interactions: Interaction[] = [];
  consumed: boolean[] = [];
  seqCounter = 0;

  report: Report;
  private recordFd: number | null = null;

  constructor(cassettePath: string, opts: CassetteOptions = {}) {
    this.path = cassettePath;
    const envMode = (process.env.AGENTREPLAY_MODE as Mode | undefined) || undefined;
    this.mode = envMode || opts.mode || "auto";
    this.onMiss = opts.onMiss || "error";
    this.divergencePolicy = opts.divergence || "warn";
    this.requireAllPlayed = opts.requireAllPlayed ?? false;
    this.streamTiming = opts.streamTiming || "none";
    this.allowPassthroughHosts = new Set(
      (opts.allowPassthroughHosts || []).map((h) => h.toLowerCase())
    );
    this.includeHeaders = new Set((opts.includeHeaders || []).map((h) => h.toLowerCase()));
    this.labels = opts.labels || {};
    this.ignorePaths = [...(opts.ignorePaths || [])];
    this.presets = [...(opts.presets || [])];
    this.redact = [...(opts.redact || [])];
    this.report = new Report(this.mode, this.path);
  }

  open(): void {
    this.resolveMode();
    if (this.effectiveMode === "replay") this.load();
    else if (this.effectiveMode === "record") this.openRecord();
  }

  close(): void {
    if (this.recordFd !== null) {
      fs.closeSync(this.recordFd);
      this.recordFd = null;
    }
    if (this.effectiveMode === "replay") {
      const unused = this.consumed
        .map((c, i) => (c ? -1 : i))
        .filter((i) => i >= 0);
      for (const i of unused) {
        const it = this.interactions[i];
        this.report.add({
          kind: "flow_unused",
          detail: `interaction ${it.id} (seq=${it.seq}) was recorded but never replayed`,
        });
      }
      if (unused.length > 0 && this.requireAllPlayed) {
        throw new DivergenceError(
          `${unused.length} unused interactions and requireAllPlayed=true`
        );
      }
    }
  }

  private resolveMode(): void {
    let m = this.mode;
    if (m === "auto") {
      if (fs.existsSync(this.path)) m = "replay";
      else {
        m = "record";
        console.log(`[agent-replay] recording new cassette: ${this.path}`);
      }
    }
    this.effectiveMode = m;
    this.report.mode = m;
  }

  private load(): void {
    if (!fs.existsSync(this.path)) throw new CassetteFormatError(`cassette not found: ${this.path}`);
    const text = fs.readFileSync(this.path, "utf-8");
    const lines = text.split("\n").filter((l) => l.trim().length > 0);
    if (lines.length === 0) throw new CassetteFormatError(`empty cassette: ${this.path}`);
    let headerObj: any;
    try {
      headerObj = JSON.parse(lines[0]);
    } catch (e) {
      throw new CassetteFormatError(`bad header JSON: ${(e as Error).message}`);
    }
    if (headerObj.kind !== "header") throw new CassetteFormatError("first line is not a header");
    this.header = headerObj as CassetteHeader;
    this.interactions = [];
    for (let i = 1; i < lines.length; i++) {
      let obj: any;
      try {
        obj = JSON.parse(lines[i]);
      } catch (e) {
        throw new CassetteFormatError(`bad interaction JSON on line ${i + 1}`);
      }
      if (obj.kind !== "interaction")
        throw new CassetteFormatError(`line ${i + 1} is not an interaction`);
      this.interactions.push(obj as Interaction);
    }
    this.consumed = new Array(this.interactions.length).fill(false);
    this.seqCounter = this.interactions.reduce((m, it) => Math.max(m, it.seq), 0);

    // Runtime overrides fall back to header when not provided.
    if (this.ignorePaths.length === 0) this.ignorePaths = [...(this.header.normalization.ignore_paths || [])];
    if (this.presets.length === 0) this.presets = [...(this.header.normalization.presets || [])];
    if (this.redact.length === 0) this.redact = [...(this.header.redaction_rules || [])];
  }

  private openRecord(): void {
    fs.mkdirSync(path.dirname(this.path), { recursive: true });
    this.header = {
      kind: "header",
      format_version: FORMAT_VERSION,
      library: LIBRARY_NAME,
      library_version: LIBRARY_VERSION,
      created_at: new Date().toISOString().replace(/\.\d+Z$/, "Z"),
      normalization: { ignore_paths: [...this.ignorePaths], presets: [...this.presets] },
      redaction_rules: [...this.redact],
      labels: this.labels,
    };
    this.recordFd = fs.openSync(this.path, "w");
    fs.writeSync(this.recordFd, canonicalJSON(this.header) + "\n");
  }

  applyRedaction(body: unknown): unknown {
    return applyRedaction(body, this.redact);
  }

  computeFingerprints(method: string, host: string, urlPath: string, body: unknown): [string, string] {
    const exact = computeFp(method, host, urlPath, body);
    const norm = computeFp(method, host, urlPath, body, {
      ignorePaths: this.ignorePaths,
      presets: this.presets,
    });
    return [exact, norm];
  }

  lookup(method: string, host: string, urlPath: string, body: unknown): Interaction | null {
    const redacted = this.applyRedaction(body);
    const [fpExact, fpNorm] = this.computeFingerprints(method, host, urlPath, redacted);
    this.report.interactionsSeen += 1;
    const candidates = this.interactions
      .map((it, idx) => ({ it, idx }))
      .filter(({ it, idx }) => !this.consumed[idx] && it.host === host.toLowerCase() && it.path === urlPath);
    if (candidates.length === 0) return null;
    for (const { it, idx } of candidates) {
      if (it.request.fp_exact === fpExact) return this.consume(idx);
    }
    for (const { it, idx } of candidates) {
      if (it.request.fp_norm === fpNorm) return this.consume(idx);
    }
    const chosen = candidates.reduce((a, b) => (a.it.seq < b.it.seq ? a : b));
    const diff = jsonDiff(chosen.it.request.body, redacted);
    this.report.add({
      kind: "request",
      detail: `fingerprint mismatch on ${method} ${host}${urlPath}; fell back to seq=${chosen.it.seq}`,
      diff,
    });
    if (this.divergencePolicy === "error") {
      throw new DivergenceError(
        `request divergence on ${method} ${host}${urlPath} (seq=${chosen.it.seq})`
      );
    }
    if (this.divergencePolicy === "warn") {
      console.warn(
        `[agent-replay] WARN: request divergence on ${method} ${host}${urlPath} (seq=${chosen.it.seq})`
      );
    }
    return this.consume(chosen.idx);
  }

  private consume(i: number): Interaction {
    this.consumed[i] = true;
    this.report.interactionsPlayed += 1;
    return this.interactions[i];
  }

  record(args: {
    method: string;
    host: string;
    path: string;
    requestBody: unknown;
    responseStatus: number;
    responseBody: unknown;
    responseStream: { delay_ms: number; data: string }[] | null;
    requestHeaders?: Record<string, string>;
    responseHeaders?: Record<string, string>;
    startedAt?: string;
    latencyMs?: number;
  }): Interaction {
    const redacted = this.applyRedaction(args.requestBody);
    const [fpExact, fpNorm] = this.computeFingerprints(args.method, args.host, args.path, redacted);
    const provider = detect(args.host, args.path);
    this.seqCounter += 1;
    const seq = this.seqCounter;
    const inter: Interaction = {
      kind: "interaction",
      id: `int_${String(seq).padStart(4, "0")}`,
      seq,
      provider,
      method: args.method.toUpperCase(),
      host: args.host.toLowerCase(),
      path: args.path,
      request: { body: redacted, fp_exact: fpExact, fp_norm: fpNorm },
      response: {
        status: args.responseStatus,
        body: args.responseBody,
        stream: args.responseStream,
      },
    };
    if (args.requestHeaders) inter.request.headers = args.requestHeaders;
    if (args.responseHeaders) inter.response.headers = args.responseHeaders;
    if (args.startedAt || args.latencyMs !== undefined) {
      inter.timing = { started_at: args.startedAt ?? null, latency_ms: args.latencyMs ?? null };
    }
    if (this.recordFd !== null) {
      fs.writeSync(this.recordFd, canonicalJSON(inter) + "\n");
    }
    this.interactions.push(inter);
    this.consumed.push(true);
    this.report.interactionsRecorded += 1;
    this.report.interactionsSeen += 1;
    this.report.interactionsPlayed += 1;
    return inter;
  }
}

export { AgentReplayError, DivergenceError, CassetteMissError };
