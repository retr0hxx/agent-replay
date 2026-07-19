"""Command-line interface: ``agentreplay {inspect,show,verify}``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .cassette import CassetteHeader, Interaction
from .canonical import canonical_json
from .fingerprint import fingerprint as compute_fp
from .redaction import apply_redaction


def _read_cassette(path: str) -> tuple[CassetteHeader, list[Interaction]]:
    text = Path(path).read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        print(f"error: empty cassette: {path}", file=sys.stderr)
        raise SystemExit(2)
    header = CassetteHeader.from_json(json.loads(lines[0]))
    interactions = [Interaction.from_json(json.loads(ln)) for ln in lines[1:]]
    return header, interactions


def _summary(text: Any, limit: int = 80) -> str:
    s = json.dumps(text, ensure_ascii=False)
    if len(s) > limit:
        return s[: limit - 3] + "..."
    return s


def cmd_inspect(args) -> int:
    header, ints = _read_cassette(args.cassette)
    print(f"cassette : {args.cassette}")
    print(f"format   : v{header.format_version}  library={header.library}@{header.library_version}")
    print(f"created  : {header.created_at}")
    print(f"presets  : {header.normalization.get('presets') or []}")
    print(f"ignore   : {header.normalization.get('ignore_paths') or []}")
    print(f"redact   : {len(header.redaction_rules)} rule(s)")
    print(f"interact : {len(ints)}")
    print()
    for it in ints:
        print(
            f"  seq={it.seq:>3}  {it.method} {it.host}{it.path}  "
            f"[{it.provider}] status={it.response_status}  "
            f"req={_summary(it.request_body)}"
        )
    return 0


def cmd_show(args) -> int:
    _, ints = _read_cassette(args.cassette)
    target = None
    for it in ints:
        if it.seq == args.seq:
            target = it
            break
    if target is None:
        print(f"error: no interaction with seq={args.seq}", file=sys.stderr)
        return 2
    out = target.to_json()
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def cmd_verify(args) -> int:
    header, ints = _read_cassette(args.cassette)
    errors: list[str] = []
    seen_seqs: set[int] = set()

    for i, it in enumerate(ints, 1):
        if it.seq in seen_seqs:
            errors.append(f"line {i+1}: duplicate seq={it.seq}")
        seen_seqs.add(it.seq)

        redacted = apply_redaction(it.request_body, header.redaction_rules)
        fp_exact = compute_fp(it.method, it.host, it.path, redacted)
        fp_norm = compute_fp(
            it.method,
            it.host,
            it.path,
            redacted,
            ignore_paths=header.normalization.get("ignore_paths"),
            presets=header.normalization.get("presets"),
        )
        if fp_exact != it.fp_exact:
            errors.append(f"seq={it.seq}: fp_exact mismatch (stored={it.fp_exact} recomputed={fp_exact})")
        if fp_norm != it.fp_norm:
            errors.append(f"seq={it.seq}: fp_norm mismatch (stored={it.fp_norm} recomputed={fp_norm})")

    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        print(f"\nverify: {len(errors)} error(s)", file=sys.stderr)
        return 1
    print(f"verify: OK ({len(ints)} interactions, {len(header.redaction_rules)} redaction rules)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agentreplay")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_inspect = sub.add_parser("inspect", help="Show cassette header + interaction summary")
    p_inspect.add_argument("cassette")
    p_inspect.set_defaults(func=cmd_inspect)

    p_show = sub.add_parser("show", help="Pretty-print a single interaction by seq")
    p_show.add_argument("cassette")
    p_show.add_argument("seq", type=int)
    p_show.set_defaults(func=cmd_show)

    p_verify = sub.add_parser("verify", help="Re-check structure and fingerprints")
    p_verify.add_argument("cassette")
    p_verify.set_defaults(func=cmd_verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
