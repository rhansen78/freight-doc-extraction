"""The escalation policy: which extractions a human must look at.

This is the decision the business actually cares about. Field accuracy is a
diagnostic; the operational question is "how many documents can post without
review, and how many bad ones slip through when they do?"

Threshold discipline
--------------------
`CONFIDENCE_FLOOR` was chosen on the development split and then frozen before
the held-out corpus was scored. It is recorded here, in code, with the date and
the split it came from, so that a future change is visible in a diff rather
than absorbed silently into a better-looking number.

Tuning the threshold on the same corpus you report is how eval harnesses come
to describe a system that does not exist. See docs/EVAL.md.
"""
from __future__ import annotations

from dataclasses import dataclass

from .schema import CRITICAL_FIELDS, Extraction
from .validate import Issue, has_errors

# Frozen 2026-08-23 on the dev split (seed 20260823, n=60, docs 0-29).
# Held-out scoring uses docs 30-59 and does not touch this value.
CONFIDENCE_FLOOR = 0.75

# A document may be posted with at most this many non-critical fields
# unresolved. Missing optional data is a cost; inventing it is a defect.
MAX_UNRESOLVED_NONCRITICAL = 3


@dataclass(frozen=True)
class Decision:
    escalate: bool
    reasons: tuple[str, ...]

    @property
    def auto_post(self) -> bool:
        return not self.escalate


def decide(ex: Extraction, issues: list[Issue]) -> Decision:
    reasons: list[str] = []

    if has_errors(issues):
        errs = sorted({i.rule for i in issues if i.severity == "error"})
        reasons.append("validation_error:" + ",".join(errs))

    missing_critical = [n for n in CRITICAL_FIELDS if ex.fields.get(n) is None]
    if missing_critical:
        reasons.append("critical_unresolved:" + ",".join(missing_critical))

    conf = ex.min_confidence()
    if conf < CONFIDENCE_FLOOR:
        reasons.append(f"low_confidence:{conf:.2f}<{CONFIDENCE_FLOOR}")

    noncritical_unresolved = [
        n for n in ex.fields_unresolved if n not in CRITICAL_FIELDS
    ]
    if len(noncritical_unresolved) > MAX_UNRESOLVED_NONCRITICAL:
        reasons.append(f"sparse_document:{len(noncritical_unresolved)}_unresolved")

    return Decision(escalate=bool(reasons), reasons=tuple(reasons))
