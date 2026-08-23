"""Extractors: the thing under test.

Two implementations ship here.

`ClaudeExtractor` is the real one. It asks a model for a single structured
tool call and gives it one instruction that matters more than the rest: a field
that is not printed on the document must come back null and be listed in
fields_unresolved. Never inferred, never carried over from a similar invoice,
never computed. The eval measures whether that instruction holds.

`StubExtractor` is a deterministic fake used by the test suite and by CI. It
reads the ground truth and then damages it in specified ways -- wrong values,
silent nulls, invented values for absent fields -- so the metric code can be
tested without an API key and without spending money. It proves the harness
detects failures; it says nothing about any model's quality, and the eval
report labels any run that used it.
"""
from __future__ import annotations

import json
import os
import random
import time
from typing import Protocol

from .schema import ALL_FIELDS, Document, Extraction, LineItem

SYSTEM_PROMPT = """\
You extract structured data from freight invoices. You are precise and you do \
not guess.

Rules, in priority order:

1. Return a value ONLY if it is printed on the document. If a field is not \
present, return null for it and list its name in fields_unresolved. This \
matters more than completeness: a null is a correct answer, an invented value \
is a defect that costs more to find than the missing field would have cost.
2. Do not compute fields that are not printed. If the document shows a subtotal \
and a total but no VAT amount, vat_amount is null -- do not subtract.
3. Do not normalise away information. Copy identifiers exactly as printed, \
including prefixes and separators.
4. Dates as ISO 8601 (YYYY-MM-DD). Money as a plain decimal string with no \
thousands separators and no currency symbol. Currency as a 3-letter ISO code.
5. Give each field a confidence in [0, 1] reflecting how clearly you could read \
it. Documents may be OCR-corrupted; a value you reconstructed from a damaged \
string should carry lower confidence than one you read cleanly.
"""

TOOL_SCHEMA = {
    "name": "record_invoice",
    "description": "Record the fields extracted from a freight invoice.",
    "input_schema": {
        "type": "object",
        "properties": {
            "fields": {
                "type": "object",
                "description": "Field name -> value, or null when not present on the document.",
                "properties": {name: {"type": ["string", "number", "null"]} for name in ALL_FIELDS},
            },
            "fields_unresolved": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Names of fields not printed on this document.",
            },
            "confidence": {
                "type": "object",
                "description": "Field name -> confidence in [0,1].",
                "additionalProperties": {"type": "number"},
            },
            "line_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "description": {"type": "string"},
                        "quantity": {"type": "integer"},
                        "unit_price": {"type": "string"},
                        "amount": {"type": "string"},
                    },
                    "required": ["description", "quantity", "unit_price", "amount"],
                },
            },
        },
        "required": ["fields", "fields_unresolved", "confidence"],
    },
}


class Extractor(Protocol):
    name: str

    def extract(self, doc: Document) -> Extraction: ...


# --------------------------------------------------------------------------- #
# Real extractor
# --------------------------------------------------------------------------- #
# Pricing is a runtime input, not a constant baked into the harness: rates
# change, and a stale constant silently misreports cost per document.
_PRICE_IN = float(os.environ.get("FDE_PRICE_IN_PER_MTOK", "0") or 0)
_PRICE_OUT = float(os.environ.get("FDE_PRICE_OUT_PER_MTOK", "0") or 0)


class ClaudeExtractor:
    """Single-turn structured extraction via the Anthropic Messages API."""

    def __init__(self, model: str | None = None, max_tokens: int = 2048):
        self.model = model or os.environ.get("FDE_MODEL", "claude-sonnet-4-5")
        self.max_tokens = max_tokens
        self.name = f"claude:{self.model}"

    def extract(self, doc: Document) -> Extraction:
        import anthropic  # imported lazily so the stub path needs no SDK

        client = anthropic.Anthropic()
        t0 = time.perf_counter()
        resp = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=SYSTEM_PROMPT,
            tools=[TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "record_invoice"},
            messages=[{
                "role": "user",
                "content": f"<document>\n{doc.text}\n</document>",
            }],
        )
        latency_ms = (time.perf_counter() - t0) * 1000

        payload = next(
            (b.input for b in resp.content if getattr(b, "type", "") == "tool_use"),
            None,
        )
        if payload is None:
            # A model that returns no tool call has not extracted anything. That
            # is a failed document, not an empty one -- record it as such rather
            # than letting it score as "everything unresolved".
            return Extraction(
                fields={n: None for n in ALL_FIELDS},
                fields_unresolved=list(ALL_FIELDS),
                confidence={n: 0.0 for n in ALL_FIELDS},
                latency_ms=latency_ms,
            )

        if isinstance(payload, str):
            payload = json.loads(payload)

        items = [
            LineItem(**it) for it in payload.get("line_items", []) or []
        ]
        u = resp.usage
        cost = (u.input_tokens / 1e6) * _PRICE_IN + (u.output_tokens / 1e6) * _PRICE_OUT

        return Extraction(
            fields=payload.get("fields", {}) or {},
            fields_unresolved=payload.get("fields_unresolved", []) or [],
            confidence=payload.get("confidence", {}) or {},
            line_items=items,
            latency_ms=latency_ms,
            input_tokens=u.input_tokens,
            output_tokens=u.output_tokens,
            cost_usd=cost if (_PRICE_IN or _PRICE_OUT) else None,
        )


# --------------------------------------------------------------------------- #
# Deterministic stub
# --------------------------------------------------------------------------- #
class StubExtractor:
    """Fake extractor with injectable, seeded failure modes.

    Used to test that the harness *detects* each failure mode. It is not a
    baseline and must never be reported as one.
    """

    is_stub = True

    def __init__(
        self,
        seed: int = 7,
        wrong_rate: float = 0.06,
        hallucinate_rate: float = 0.30,
        silent_null_rate: float = 0.03,
        name: str = "stub",
    ):
        self.rng = random.Random(seed)
        self.wrong_rate = wrong_rate
        self.hallucinate_rate = hallucinate_rate
        self.silent_null_rate = silent_null_rate
        self.name = name

    def extract(self, doc: Document) -> Extraction:
        fields: dict = {}
        unresolved: list[str] = []
        conf: dict[str, float] = {}
        truth = doc.truth
        absent = set(doc.absent_fields)

        for name in ALL_FIELDS:
            if name in absent:
                # The probe: does the extractor invent a value for a field the
                # document does not contain?
                if self.rng.random() < self.hallucinate_rate:
                    fields[name] = self._invent(name, truth)
                    conf[name] = round(self.rng.uniform(0.55, 0.9), 2)
                else:
                    fields[name] = None
                    unresolved.append(name)
                    conf[name] = 0.0
                continue

            val = getattr(truth, name, None)
            val = None if val is None else (val.isoformat() if hasattr(val, "isoformat") else str(val))

            if val is not None and self.rng.random() < self.wrong_rate:
                val = self._corrupt(name, val)
                conf[name] = round(self.rng.uniform(0.4, 0.8), 2)
            elif val is not None and self.rng.random() < self.silent_null_rate:
                # Dropped without declaring it -- the validator should catch this.
                fields[name] = None
                conf[name] = 0.0
                continue
            else:
                conf[name] = round(self.rng.uniform(0.85, 0.99), 2)

            fields[name] = val
            if val is None and name not in unresolved:
                unresolved.append(name)

        items = [
            LineItem(
                description=i.description,
                quantity=i.quantity,
                unit_price=i.unit_price,
                amount=i.amount,
            )
            for i in truth.line_items
        ]
        return Extraction(
            fields=fields,
            fields_unresolved=unresolved,
            confidence=conf,
            line_items=items,
            latency_ms=self.rng.uniform(400, 1400),
            input_tokens=len(doc.text) // 4,
            output_tokens=180,
        )

    def _invent(self, name: str, truth) -> str:
        if "date" in name:
            return truth.invoice_date.isoformat()
        if name == "parcel_count":
            return str(self.rng.randint(1, 200))
        if name == "supplier_vat":
            return f"DK{self.rng.randint(10**7, 10**8)}"
        if name == "shipment_ref":
            return f"SHP{self.rng.randint(10**6, 10**7 - 1)}"
        if name == "vat_rate":
            return "0.25"
        if name == "customer_name":
            return "Kolding Retail Holding A/S"
        return str(round(self.rng.uniform(10, 900), 2))

    def _corrupt(self, name: str, val: str) -> str:
        if any(c.isdigit() for c in val):
            digits = [i for i, c in enumerate(val) if c.isdigit()]
            i = self.rng.choice(digits)
            return val[:i] + str((int(val[i]) + 1) % 10) + val[i + 1:]
        return val + "X"
