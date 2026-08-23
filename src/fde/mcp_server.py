#!/usr/bin/env python3
"""MCP server exposing the extraction pipeline as tools.

    fde-mcp                      # stdio, for a desktop client
    python -m fde.mcp_server

Why an MCP server rather than a REST API: the consumer here is an agent, not a
browser. The tools are shaped for that -- each returns the validation issues and
the escalation decision alongside the values, so a calling agent can tell the
difference between "here is the data" and "here is data you should not act on".
A REST endpoint that returned only the fields would leave the caller to guess.

`extract_document` deliberately does NOT return a bare dict of values. Making
the caller receive `escalate` in the same payload is the whole safety argument.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from fde.extract import ClaudeExtractor, StubExtractor  # noqa: E402
from fde.generate import build_corpus                   # noqa: E402
from fde.policy import decide                           # noqa: E402
from fde.schema import Document, FreightInvoice         # noqa: E402
from fde.validate import validate                       # noqa: E402

mcp = FastMCP("freight-doc-extraction")


def _extractor():
    if os.environ.get("FDE_EXTRACTOR", "claude") == "stub":
        return StubExtractor()
    return ClaudeExtractor()


def _wrap(doc: Document) -> dict:
    ex = _extractor().extract(doc)
    issues = validate(ex)
    dec = decide(ex, issues)
    return {
        "fields": ex.fields,
        "fields_unresolved": ex.fields_unresolved,
        "confidence": ex.confidence,
        "line_items": [i.model_dump(mode="json") for i in ex.line_items],
        "validation_issues": [
            {"rule": i.rule, "severity": i.severity, "message": i.message}
            for i in issues
        ],
        "escalate": dec.escalate,
        "escalation_reasons": list(dec.reasons),
        "latency_ms": ex.latency_ms,
    }


@mcp.tool()
def extract_document(text: str) -> str:
    """Extract structured fields from freight invoice text.

    Returns the extracted fields together with validation issues and an
    escalation decision. If `escalate` is true, the values have not passed
    validation and must not be posted without human review.
    """
    doc = Document(
        doc_id="adhoc",
        text=text,
        layout="unknown",
        truth=FreightInvoice(
            invoice_number="", invoice_date="2026-01-01",
            supplier_name="", currency="EUR", total="0",
        ),
    )
    return json.dumps(_wrap(doc), indent=2, default=str)


@mcp.tool()
def validate_fields(fields_json: str) -> str:
    """Run the deterministic validation rules over an already-extracted payload.

    Useful for checking a payload that came from somewhere else -- a different
    extractor, a manual entry, an upstream system. Runs no model.
    """
    from fde.schema import Extraction

    payload = json.loads(fields_json)
    ex = Extraction(**payload) if "fields" in payload else Extraction(fields=payload)
    issues = validate(ex)
    dec = decide(ex, issues)
    return json.dumps({
        "validation_issues": [
            {"rule": i.rule, "severity": i.severity, "message": i.message}
            for i in issues
        ],
        "escalate": dec.escalate,
        "escalation_reasons": list(dec.reasons),
    }, indent=2)


@mcp.tool()
def sample_document(index: int = 0, seed: int = 20260823) -> str:
    """Return one synthetic freight invoice from the evaluation corpus.

    Includes which fields were deliberately omitted from the rendering, so a
    caller can check an extraction against known ground truth.
    """
    docs = build_corpus(n=60, seed=seed)
    doc = docs[index % len(docs)]
    return json.dumps({
        "doc_id": doc.doc_id,
        "layout": doc.layout,
        "text": doc.text,
        "absent_fields": doc.absent_fields,
        "ground_truth": doc.truth.model_dump(mode="json"),
    }, indent=2, default=str)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
