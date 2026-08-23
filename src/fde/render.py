"""Render a FreightInvoice to document text in one of three layouts.

Three layouts, because a single template teaches an extractor the template
rather than the task. Each uses different label wording, different field order
and a different way of expressing the same value -- which is what real supplier
populations look like.

`scan_noise_v3` additionally applies OCR-style corruption. It is not decoration:
it is the variant that separates an extractor that reads from one that
pattern-matches on exact label strings.
"""
from __future__ import annotations

import random
from decimal import Decimal

from .schema import FreightInvoice

# Character confusions a real OCR pass produces on scanned freight paperwork.
OCR_CONFUSIONS = {
    "O": "0", "o": "0", "I": "1", "l": "1", "S": "5",
    "B": "8", "Z": "2", "g": "9",
}


def _noise(text: str, rng: random.Random, rate: float = 0.012) -> str:
    """Corrupt a small fraction of characters, and break some spacing.

    Deliberately mild. The goal is to make exact-string matching brittle, not
    to make the document unreadable -- an unreadable document tests nothing.
    Digits inside monetary amounts are left alone, because a corrupted total
    would make the ground truth wrong rather than the task hard.
    """
    out = []
    for ch in text:
        if ch.isalpha() and ch in OCR_CONFUSIONS and rng.random() < rate:
            out.append(OCR_CONFUSIONS[ch])
        elif ch == " " and rng.random() < rate:
            out.append("  ")
        else:
            out.append(ch)
    return "".join(out)


def _fmt(v: Decimal | int | str | None) -> str:
    return "" if v is None else str(v)


def _tabular(inv: FreightInvoice, absent: set[str]) -> str:
    L = []
    L.append(f"{inv.supplier_name}")
    if "supplier_vat" not in absent:
        L.append(f"VAT Reg. No: {inv.supplier_vat}")
    L.append("")
    L.append("FREIGHT INVOICE")
    L.append(f"Invoice No.       {inv.invoice_number}")
    L.append(f"Invoice Date      {inv.invoice_date.isoformat()}")
    if "due_date" not in absent:
        L.append(f"Payment Due       {inv.due_date.isoformat()}")
    if "customer_name" not in absent:
        L.append(f"Bill To           {inv.customer_name}")
    if "shipment_ref" not in absent:
        L.append(f"Shipment Ref.     {inv.shipment_ref}")
    L.append("")
    L.append("Description                              Qty     Unit      Amount")
    L.append("-" * 70)
    for it in inv.line_items:
        L.append(f"{it.description:<40} {it.quantity:>5} {it.unit_price:>9} {it.amount:>11}")
    L.append("-" * 70)
    L.append(f"{'Subtotal':>56} {inv.subtotal:>11}")
    if "vat_rate" not in absent:
        L.append(f"{'VAT @ ' + str(int(inv.vat_rate * 100)) + '%':>56} {inv.vat_amount:>11}")
    else:
        L.append(f"{'VAT':>56} {inv.vat_amount:>11}")
    L.append(f"{'TOTAL ' + inv.currency:>56} {inv.total:>11}")
    L.append("")
    tail = []
    if "weight_kg" not in absent:
        tail.append(f"Gross weight: {inv.weight_kg} kg")
    if "parcel_count" not in absent:
        tail.append(f"Parcels: {inv.parcel_count}")
    if tail:
        L.append("   ".join(tail))
    return "\n".join(L)


def _narrative(inv: FreightInvoice, absent: set[str]) -> str:
    L = []
    L.append(f"{inv.supplier_name} — Statement of Charges")
    L.append("")
    intro = (
        f"This statement, reference {inv.invoice_number}, was raised on "
        f"{inv.invoice_date.strftime('%d %B %Y')}"
    )
    if "customer_name" not in absent:
        intro += f" in respect of carriage performed for {inv.customer_name}"
    if "shipment_ref" not in absent:
        intro += f" under shipment {inv.shipment_ref}"
    L.append(intro + ".")
    if "due_date" not in absent:
        L.append(f"Settlement is requested by {inv.due_date.strftime('%d %B %Y')}.")
    if "supplier_vat" not in absent:
        L.append(f"Our VAT identification is {inv.supplier_vat}.")
    L.append("")
    L.append("Charges comprised:")
    for it in inv.line_items:
        L.append(
            f"  • {it.description} — {it.quantity} at {it.unit_price} "
            f"per unit, being {it.amount}."
        )
    L.append("")
    L.append(
        f"Charges before tax amount to {inv.subtotal} {inv.currency}."
    )
    if "vat_rate" not in absent:
        L.append(
            f"Value added tax is applied at {int(inv.vat_rate * 100)} per cent, "
            f"being {inv.vat_amount} {inv.currency}."
        )
    else:
        L.append(f"Value added tax of {inv.vat_amount} {inv.currency} applies.")
    L.append(
        f"The sum now payable is {inv.total} {inv.currency}."
    )
    tail = []
    if "weight_kg" not in absent:
        tail.append(f"a gross weight of {inv.weight_kg} kilogrammes")
    if "parcel_count" not in absent:
        tail.append(f"{inv.parcel_count} parcels")
    if tail:
        L.append("")
        L.append("The consignment comprised " + " and ".join(tail) + ".")
    return "\n".join(L)


def render(
    inv: FreightInvoice,
    layout: str,
    absent: list[str] | None = None,
    rng: random.Random | None = None,
) -> str:
    absent_set = set(absent or [])
    if layout == "narrative_v2":
        text = _narrative(inv, absent_set)
    else:
        text = _tabular(inv, absent_set)
    if layout == "scan_noise_v3":
        text = _noise(text, rng or random.Random(0))
    return text
