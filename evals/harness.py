#!/usr/bin/env python3
"""Run a corpus through an extractor and report.

    python evals/harness.py --extractor stub --split dev
    python evals/harness.py --extractor claude --split heldout --out evals/results

Splits exist so the confidence threshold in fde/policy.py can be chosen on dev
and reported on held-out. The harness refuses to let you quietly report a dev
number as a result: a dev run is written to a file named as such and the
markdown it produces says so at the top.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "evals"))

from fde.generate import build_corpus                    # noqa: E402
from fde.extract import ClaudeExtractor, StubExtractor   # noqa: E402
from fde.policy import CONFIDENCE_FLOOR, decide          # noqa: E402
from fde.validate import validate                        # noqa: E402
from metrics import score_document, summarise            # noqa: E402

SPLITS = {"dev": slice(0, 30), "heldout": slice(30, 60), "all": slice(0, None)}


def run(extractor, docs, verbose=False):
    scores, escalated, extractions, rows = [], [], [], []
    for doc in docs:
        ex = extractor.extract(doc)
        issues = validate(ex)
        dec = decide(ex, issues)
        sc = score_document(doc, ex)

        extractions.append(ex)
        escalated.append(dec.escalate)
        scores.append(sc)
        rows.append({
            "doc_id": doc.doc_id,
            "layout": doc.layout,
            "escalate": dec.escalate,
            "reasons": list(dec.reasons),
            "wrong_fields": sc.wrong_fields,
            "hallucinated": sc.hallucinated,
            "issues": [i.rule for i in issues],
            "defective": sc.defective,
        })
        if verbose:
            flag = "ESC " if dec.escalate else "auto"
            print(f"  {flag} {doc.doc_id} [{doc.layout}] "
                  f"wrong={len(sc.wrong_fields)} halluc={len(sc.hallucinated)}")
    return scores, escalated, extractions, rows


def to_markdown(summary, meta) -> str:
    s = summary
    lines = []
    lines.append(f"# Eval run — {meta['extractor']} / {meta['split']} split\n")
    if meta.get("is_stub"):
        lines.append(
            "> **This run used the deterministic stub extractor.** The numbers below "
            "describe injected failure modes and demonstrate that the harness detects "
            "them. They are not a measurement of any model.\n"
        )
    if meta["split"] == "dev":
        lines.append(
            "> Development split. The confidence threshold was chosen against this "
            "data, so these figures are optimistic by construction. Report the "
            "held-out split.\n"
        )
    lines.append(f"- corpus: {s.n_docs} documents, seed `{meta['seed']}`")
    lines.append(f"- confidence floor: `{CONFIDENCE_FLOOR}`\n")

    lines.append("## What matters\n")
    lines.append("| metric | value | reading |")
    lines.append("|---|---:|---|")
    lines.append(f"| **escaped defect rate** | {s.escaped_defect_rate:.1%} | "
                 "wrong documents posted with no human review |")
    lines.append(f"| **hallucination rate** | {s.hallucination_rate:.1%} | "
                 "values returned for fields not on the document |")
    lines.append(f"| absence recall | {s.absence_recall:.1%} | "
                 "absent fields correctly declared unresolved |")
    lines.append(f"| auto-post rate | {s.auto_post_rate:.1%} | documents needing no review |")
    lines.append(f"| unnecessary escalation | {s.unnecessary_escalation_rate:.1%} | "
                 "reviews of documents that were actually fine |")
    lines.append(f"| field accuracy | {s.field_accuracy:.1%} | the flattering one |")
    lines.append(f"| corpus defect rate | {s.defect_rate:.1%} | documents with any error |\n")

    lines.append("## By layout\n")
    lines.append("| layout | field accuracy |")
    lines.append("|---|---:|")
    for k, v in s.by_layout.items():
        lines.append(f"| `{k}` | {v:.1%} |")
    lines.append("")

    if s.latency_p50_ms is not None:
        lines.append("## Cost and latency\n")
        lines.append(f"- p50 latency: {s.latency_p50_ms:.0f} ms")
        lines.append(f"- p95 latency: {s.latency_p95_ms:.0f} ms")
        if s.cost_usd_total is not None:
            lines.append(f"- total cost: ${s.cost_usd_total:.4f} "
                         f"(${s.cost_usd_total / max(s.n_docs, 1):.5f}/doc)")
        else:
            lines.append("- cost: not computed (set FDE_PRICE_IN_PER_MTOK / "
                         "FDE_PRICE_OUT_PER_MTOK to price a run)")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--extractor", choices=["stub", "claude"], default="stub")
    ap.add_argument("--split", choices=list(SPLITS), default="heldout")
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--seed", type=int, default=20260823)
    ap.add_argument("--model", default=None)
    ap.add_argument("--out", default=None, help="directory for results.json / results.md")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--fail-over", type=float, default=None,
                    help="exit 1 if escaped defect rate exceeds this (for CI gating)")
    args = ap.parse_args()

    docs = build_corpus(n=args.n, seed=args.seed)[SPLITS[args.split]]
    extractor = StubExtractor() if args.extractor == "stub" else ClaudeExtractor(args.model)
    is_stub = getattr(extractor, "is_stub", False)

    print(f"Running {extractor.name} over {len(docs)} documents ({args.split} split)")
    scores, escalated, extractions, rows = run(extractor, docs, args.verbose)
    summary = summarise(scores, escalated, extractions)

    meta = {
        "extractor": extractor.name,
        "split": args.split,
        "seed": args.seed,
        "is_stub": is_stub,
        "confidence_floor": CONFIDENCE_FLOOR,
    }
    md = to_markdown(summary, meta)
    print("\n" + md)

    if args.out:
        outdir = Path(args.out)
        outdir.mkdir(parents=True, exist_ok=True)
        stem = f"{args.split}_{extractor.name.replace(':', '_')}"
        (outdir / f"{stem}.json").write_text(
            json.dumps({"meta": meta, "summary": summary.as_dict(), "documents": rows}, indent=2)
        )
        (outdir / f"{stem}.md").write_text(md)
        print(f"wrote {outdir / stem}.json and .md")

    if args.fail_over is not None and summary.escaped_defect_rate > args.fail_over:
        print(f"FAIL: escaped defect rate {summary.escaped_defect_rate:.1%} "
              f"exceeds gate {args.fail_over:.1%}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
