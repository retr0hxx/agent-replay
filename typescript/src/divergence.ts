import type { DiffRecord } from "./diff.js";

export type DivergenceKind = "request" | "flow_over" | "flow_unused";

export interface Divergence {
  kind: DivergenceKind;
  detail: string;
  diff?: DiffRecord[];
}

export class Report {
  mode: string;
  cassettePath: string;
  interactionsSeen = 0;
  interactionsPlayed = 0;
  interactionsRecorded = 0;
  divergences: Divergence[] = [];

  constructor(mode: string, cassettePath: string) {
    this.mode = mode;
    this.cassettePath = cassettePath;
  }

  add(d: Divergence): void {
    this.divergences.push(d);
  }

  toJSON(): unknown {
    return {
      mode: this.mode,
      cassette_path: this.cassettePath,
      interactions_seen: this.interactionsSeen,
      interactions_played: this.interactionsPlayed,
      interactions_recorded: this.interactionsRecorded,
      divergences: this.divergences,
    };
  }

  summary(): string {
    const lines = [
      `agent-replay report (${this.mode})`,
      `  cassette         : ${this.cassettePath}`,
      `  interactions seen: ${this.interactionsSeen}`,
      `  played           : ${this.interactionsPlayed}`,
      `  recorded         : ${this.interactionsRecorded}`,
      `  divergences      : ${this.divergences.length}`,
    ];
    this.divergences.forEach((d, idx) => {
      lines.push(`  [${idx + 1}] ${d.kind}: ${d.detail}`);
      if (d.diff) {
        for (const c of d.diff.slice(0, 5)) {
          lines.push(`      - ${c.path} (${c.op})`);
        }
        if (d.diff.length > 5) lines.push(`      ... ${d.diff.length - 5} more`);
      }
    });
    return lines.join("\n");
  }
}
