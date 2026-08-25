"""Synthetic freight-invoice generator.

Ground truth comes first; the document is rendered from it. That ordering is
the whole reason this corpus is usable as an evaluation set:

  * the labels are exact, not annotated, so there is no labelling error floor;
  * we know which fields were deliberately omitted from the rendering, which
    turns hallucination into something measurable rather than anecdotal;
  * the corpus regenerates identically from a seed, so an eval run is
    reproducible and a regression is attributable to the extractor.

No real supplier, customer, rate or document is used. Everything below is
invented from fixed word lists.
"""
from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from .schema import Document, FreightInvoice, LineItem

CARRIERS = [
    "Nordfragt Logistik A/S", "Baltic Parcel Group", "Vestbro Transport ApS",
    "Kattegat Freight Services", "Meridian Cargo BV", "Sundbro Distribution AB",
    "Harbourline Shipping Oy", "Elbe Overland GmbH",
]
CUSTOMERS = [
    "Kolding Retail Holding A/S", "Nordic Home Supply ApS", "Bergen Trading AS",
    "Malmö Grossist AB", "Aarhus Components A/S", "Helsinki Parts Oy",
]
SERVICES = [
    "Road freight, groupage", "Express parcel service", "Palletised distribution",
    "Customs clearance handling", "Fuel surcharge", "Terminal handling",
    "Waiting time, per hour", "Residential delivery surcharge",
    "Oversize parcel handling", "Weekend delivery premium",
]
CURRENCIES = ["EUR", "DKK", "SEK", "NOK"]
LAYOUTS = ("tabular_v1", "narrative_v2", "scan_noise_v3")

# Fields the generator is allowed to omit from a rendering. Critical fields are
# never omitted -- a document without an invoice number is a different problem
# (document classification), not an extraction problem.
OMITTABLE = (
    "due_date", "supplier_vat", "customer_name", "shipment_ref",
    "weight_kg", "parcel_count", "vat_rate",
)


def _money(x: Decimal | float) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def make_invoice(rng: random.Random, idx: int) -> FreightInvoice:
    inv_date = date(2026, 1, 1) + timedelta(days=rng.randint(0, 210))
    currency = rng.choice(CURRENCIES)
    n_items = rng.randint(1, 5)

    items: list[LineItem] = []
    for _ in range(n_items):
        qty = rng.randint(1, 40)
        unit = _money(rng.uniform(4.5, 320.0))
        items.append(
            LineItem(
                description=rng.choice(SERVICES),
                quantity=qty,
                unit_price=unit,
                amount=_money(unit * qty),
            )
        )

    subtotal = _money(sum(i.amount for i in items))
    vat_rate = Decimal(rng.choice(["0.25", "0.24", "0.19", "0.00"]))
    vat_amount = _money(subtotal * vat_rate)
    total = _money(subtotal + vat_amount)

    return FreightInvoice(
        invoice_number=f"{rng.choice(['INV', 'FR', 'NL'])}-{2026}{rng.randint(10000, 99999)}",
        invoice_date=inv_date,
        due_date=inv_date + timedelta(days=rng.choice([14, 30, 45])),
        supplier_name=rng.choice(CARRIERS),
        supplier_vat=f"{rng.choice(['DK', 'SE', 'NO', 'NL', 'DE'])}{rng.randint(10**7, 10**9)}",
        customer_name=rng.choice(CUSTOMERS),
        currency=currency,
        shipment_ref=f"SHP{rng.randint(10**6, 10**7 - 1)}",
        subtotal=subtotal,
        vat_rate=vat_rate,
        vat_amount=vat_amount,
        total=total,
        weight_kg=_money(rng.uniform(12, 4800)),
        parcel_count=rng.randint(1, 260),
        line_items=items,
    )


def choose_absent(rng: random.Random, p: float, truth: FreightInvoice) -> list[str]:
    """Pick fields to omit from the rendering. Never a critical field.

    Omission must be *unambiguous*, or the hallucination probe is unfair. Two
    cases are excluded:

      * a zero VAT rate, because a document showing 0.00 VAT lets a reader infer
        the rate legitimately -- returning 0 there is reasoning, not invention;
      * any value whose printed form still appears elsewhere in the document,
        which would make "did the extractor invent this?" unanswerable.

    The second check runs in build_corpus, after rendering, because whether a
    string survives depends on the layout.
    """
    out = []
    for f in OMITTABLE:
        if rng.random() >= p:
            continue
        if f == "vat_rate" and truth.vat_rate == Decimal("0.00"):
            continue
        out.append(f)
    return out


def build_corpus(
    n: int = 60,
    seed: int = 20260823,
    absent_prob: float = 0.22,
) -> list[Document]:
    """Deterministic corpus. Same seed -> byte-identical documents."""
    from .render import render

    rng = random.Random(seed)
    docs: list[Document] = []
    for i in range(n):
        truth = make_invoice(rng, i)
        layout = LAYOUTS[i % len(LAYOUTS)]
        absent = choose_absent(rng, absent_prob, truth)
        text = render(truth, layout=layout, absent=absent, rng=rng)
        # Drop any omission whose value is still visible elsewhere in the
        # rendered text -- see choose_absent. Silently keeping it would inflate
        # the measured hallucination rate with cases that are not inventions.
        absent = [
            f for f in absent
            if getattr(truth, f, None) is None or str(getattr(truth, f)) not in text
        ]
        docs.append(
            Document(
                doc_id=f"doc_{i:04d}",
                text=text,
                layout=layout,
                truth=truth,
                absent_fields=absent,
            )
        )
    return docs
