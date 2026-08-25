"""Typed schema for a freight invoice, plus the extraction envelope.

The schema is deliberately small but includes the three things that make
freight documents interesting to extract:

  * arithmetic that must reconcile (line items -> subtotal -> VAT -> total),
  * cross-references that must agree (shipment ref appears twice),
  * fields that are legitimately absent on some documents.

The third is the point. An extractor that always returns a value scores well
on accuracy and is useless in production, because you cannot tell a real
reading from an invention. Absence has to be representable.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

# Fields an operator must have before an invoice can be posted without review.
CRITICAL_FIELDS = (
    "invoice_number",
    "invoice_date",
    "supplier_name",
    "currency",
    "total",
)

ALL_FIELDS = (
    *CRITICAL_FIELDS,
    "due_date",
    "supplier_vat",
    "customer_name",
    "shipment_ref",
    "subtotal",
    "vat_rate",
    "vat_amount",
    "weight_kg",
    "parcel_count",
)


class LineItem(BaseModel):
    description: str
    quantity: int
    unit_price: Decimal
    amount: Decimal


class FreightInvoice(BaseModel):
    """Ground truth for one generated document."""

    invoice_number: str
    invoice_date: date
    supplier_name: str
    currency: str
    total: Decimal

    due_date: date | None = None
    supplier_vat: str | None = None
    customer_name: str | None = None
    shipment_ref: str | None = None
    subtotal: Decimal | None = None
    vat_rate: Decimal | None = None
    vat_amount: Decimal | None = None
    weight_kg: Decimal | None = None
    parcel_count: int | None = None

    line_items: list[LineItem] = Field(default_factory=list)


class Extraction(BaseModel):
    """What an extractor returns for one document.

    `fields` maps field name -> value or None. A field the extractor could not
    find MUST be None and MUST appear in `fields_unresolved`. Returning a
    plausible guess instead is the specific failure this repo measures.
    """

    fields: dict[str, Any] = Field(default_factory=dict)
    fields_unresolved: list[str] = Field(default_factory=list)
    confidence: dict[str, float] = Field(default_factory=dict)
    format_variant: str | None = None
    line_items: list[LineItem] = Field(default_factory=list)

    # Telemetry, filled by the runner rather than the extractor.
    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None

    def get(self, name: str) -> Any:
        return self.fields.get(name)

    def min_confidence(self, names: tuple[str, ...] = CRITICAL_FIELDS) -> float:
        vals = [self.confidence.get(n, 0.0) for n in names]
        return min(vals) if vals else 0.0


class Document(BaseModel):
    """A generated document: rendered text, its ground truth, and its provenance."""

    doc_id: str
    text: str
    layout: str
    truth: FreightInvoice
    absent_fields: list[str] = Field(default_factory=list)
    """Fields genuinely not printed on this document.

    The hallucination probe: any non-null value returned for one of these is
    an invention, by construction. This is knowable only because the document
    was generated from the truth rather than labelled after the fact.
    """
