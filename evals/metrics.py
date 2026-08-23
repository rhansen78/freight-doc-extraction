"""Metrics.

Ordered by how much anyone should care.

1. `escaped_defect_rate` -- of the documents the system posted without review,
   how many were wrong. This is the number that costs money. Everything else on
   this list is a diagnostic for it.
2. `hallucination_rate` -- of the fields genuinely absent from a document, how
   often a value came back anyway. Measurable only because the corpus is
   generated: we know what was omitted.
3. `absence_recall` -- of those absent fields, how often the extractor said so
   explicitly instead of dropping them silently.
4. `field_accuracy` -- the number everyone reports and the one that misleads
   most, because an extractor that invents plausible values scores well on it.
5. Review burden and its waste: what fraction gets escalated, and how much of
   that escalation was unnecessary.

A system can post 95% of documents unattended with 0.5% escaped defects, or
post 60% with 0%. Which is better is a business decision about the cost of a
wrong posting versus the cost of a review. The harness reports both rather than
collapsing them into one score.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from fde.schema import ALL_FIELDS, Document, Extraction


def normalise(name: str, v: Any) -> str | None:
    """Compare like with like: 1234.50 == '1234.5', '2026-06-13' == date(...)."""
    if v is None:
        return None
    s = str(v).strip()
    if s == "":
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if any(k in name for k in ("total", "subtotal", "amount", "price", "rate", "weight")):
        try:
            return str(Decimal(s.replace(",", "").replace(" ", "")).normalize())
        except (InvalidOperation, ValueError):
            return s.casefold()
    if name == "parcel_count":
        try:
            return str(int(Decimal(s)))
        except (InvalidOperation, ValueError):
            return s
    return s.casefold()


@dataclass
class DocScore:
    doc_id: str
    layout: str
    correct: int = 0
    incorrect: int = 0
    wrong_fields: list[str] = field(default_factory=list)
    hallucinated: list[str] = field(default_factory=list)
    absent_total: int = 0
    absent_declared: int = 0

    @property
    def defective(self) -> bool:
        """Any wrong value, or any value invented for an absent field."""
        return bool(self.wrong_fields or self.hallucinated)


def score_document(doc: Document, ex: Extraction) -> DocScore:
    s = DocScore(doc_id=doc.doc_id, layout=doc.layout)
    absent = set(doc.absent_fields)

    for name in ALL_FIELDS:
        got = ex.fields.get(name)
        if name in absent:
            s.absent_total += 1
            if got is not None:
                s.hallucinated.append(name)
            elif name in ex.fields_unresolved:
                s.absent_declared += 1
            continue

        want = normalise(name, getattr(doc.truth, name, None))
        if want is None:
            continue  # not on the document and not in the absent set: not scored
        if normalise(name, got) == want:
            s.correct += 1
        else:
            s.incorrect += 1
            s.wrong_fields.append(name)
    return s


@dataclass
class Summary:
    n_docs: int
    field_accuracy: float
    hallucination_rate: float
    absence_recall: float
    auto_post_rate: float
    escalation_rate: float
    escaped_defect_rate: float
    unnecessary_escalation_rate: float
    defect_rate: float
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    cost_usd_total: float | None
    by_layout: dict[str, float]

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


def summarise(
    scores: list[DocScore],
    escalated: list[bool],
    extractions: list[Extraction],
) -> Summary:
    n = len(scores)
    correct = sum(s.correct for s in scores)
    graded = correct + sum(s.incorrect for s in scores)
    absent_total = sum(s.absent_total for s in scores)
    hallucinated = sum(len(s.hallucinated) for s in scores)
    declared = sum(s.absent_declared for s in scores)

    auto = [i for i, e in enumerate(escalated) if not e]
    esc = [i for i, e in enumerate(escalated) if e]
    escaped = [i for i in auto if scores[i].defective]
    wasted = [i for i in esc if not scores[i].defective]

    lat = [e.latency_ms for e in extractions if e.latency_ms is not None]
    costs = [e.cost_usd for e in extractions if e.cost_usd is not None]

    by_layout: dict[str, float] = {}
    for layout in sorted({s.layout for s in scores}):
        sub = [s for s in scores if s.layout == layout]
        g = sum(s.correct + s.incorrect for s in sub)
        by_layout[layout] = (sum(s.correct for s in sub) / g) if g else 0.0

    return Summary(
        n_docs=n,
        field_accuracy=correct / graded if graded else 0.0,
        hallucination_rate=hallucinated / absent_total if absent_total else 0.0,
        absence_recall=declared / absent_total if absent_total else 0.0,
        auto_post_rate=len(auto) / n if n else 0.0,
        escalation_rate=len(esc) / n if n else 0.0,
        escaped_defect_rate=len(escaped) / len(auto) if auto else 0.0,
        unnecessary_escalation_rate=len(wasted) / len(esc) if esc else 0.0,
        defect_rate=sum(1 for s in scores if s.defective) / n if n else 0.0,
        latency_p50_ms=statistics.median(lat) if lat else None,
        latency_p95_ms=(sorted(lat)[max(0, int(len(lat) * 0.95) - 1)] if lat else None),
        cost_usd_total=sum(costs) if costs else None,
        by_layout=by_layout,
    )
