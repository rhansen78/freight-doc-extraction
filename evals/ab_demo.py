#!/usr/bin/env python3
"""Reproduces the two-extractor table at the top of the README.

Extractor A: reads every present field correctly, invents a value for every
absent one. Extractor B: misreads ~6% of present fields, never invents.

    python evals/ab_demo.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "evals"))

from fde.extract import StubExtractor   # noqa: E402
from fde.generate import build_corpus   # noqa: E402
from fde.policy import decide           # noqa: E402
from fde.validate import validate       # noqa: E402
from metrics import score_document, summarise  # noqa: E402

SEED = 11


def run(extractor, docs):
    scores, escalated, extractions = [], [], []
    for d in docs:
        ex = extractor.extract(d)
        extractions.append(ex)
        escalated.append(decide(ex, validate(ex)).escalate)
        scores.append(score_document(d, ex))
    return summarise(scores, escalated, extractions)


def main() -> None:
    docs = build_corpus(n=60)[30:]
    a = run(StubExtractor(seed=SEED, wrong_rate=0.0, hallucinate_rate=1.0,
                          silent_null_rate=0.0), docs)
    b = run(StubExtractor(seed=SEED, wrong_rate=0.06, hallucinate_rate=0.0,
                          silent_null_rate=0.0), docs)

    rows = [
        ("field accuracy", a.field_accuracy, b.field_accuracy),
        ("hallucination rate", a.hallucination_rate, b.hallucination_rate),
        ("auto-post rate", a.auto_post_rate, b.auto_post_rate),
        ("escaped defect rate", a.escaped_defect_rate, b.escaped_defect_rate),
    ]
    print(f"{len(docs)} held-out documents\n")
    print("| | extractor A | extractor B |")
    print("|---|---:|---:|")
    for label, av, bv in rows:
        print(f"| {label} | {av:.1%} | {bv:.1%} |")
    print("\nA has perfect field accuracy and posts the most documents unattended.")
    print("Seven in ten of those postings are wrong.")


if __name__ == "__main__":
    main()
