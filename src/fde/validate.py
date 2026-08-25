"""Deterministic validation, run after extraction and independently of it.

The architectural claim this file exists to make: do not ask the model to check
arithmetic. A language model asked "does this invoice add up?" will usually say
yes, because agreeable is the cheaper token path. Python asked the same question
is right every time, costs nothing, and its answer is auditable.

So the split is:
    model     -> reads the document, returns values or null
    validator -> decides whether those values can be true

Every rule here is cheap and total. None of them call a model.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from .schema import CRITICAL_FIELDS, Extraction

Severity = Literal["error", "warning"]

ISO_CURRENCIES = {"EUR", "DKK", "SEK", "NOK", "GBP", "USD", "PLN", "CHF"}

# Tolerance on money comparisons. Two cents, because rounding at the line level
# and rounding at the total level legitimately disagree by one cent per rounding
# step, and a freight invoice has two.
MONEY_TOL = Decimal("0.02")


@dataclass(frozen=True)
class Issue:
    rule: str
    severity: Severity
    message: str
    fields: tuple[str, ...] = ()


def _dec(v: Any) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _as_date(v: Any) -> date | None:
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        try:
            return date.fromisoformat(v[:10])
        except ValueError:
            return None
    return None


def validate(ex: Extraction) -> list[Issue]:
    issues: list[Issue] = []
    f = ex.fields

    # --- completeness -----------------------------------------------------
    for name in CRITICAL_FIELDS:
        if f.get(name) is None:
            issues.append(
                Issue("critical_field_missing", "error",
                      f"{name} is required before posting", (name,))
            )

    # --- internal consistency of the declaration --------------------------
    # A field may not be both null and absent from fields_unresolved: that
    # combination means the extractor dropped it silently, which is the one
    # behaviour the contract forbids.
    for name, val in f.items():
        if val is None and name not in ex.fields_unresolved:
            issues.append(
                Issue("silent_null", "error",
                      f"{name} returned null but was not declared unresolved", (name,))
            )

    # --- arithmetic -------------------------------------------------------
    subtotal = _dec(f.get("subtotal"))
    vat_amount = _dec(f.get("vat_amount"))
    total = _dec(f.get("total"))
    vat_rate = _dec(f.get("vat_rate"))

    if ex.line_items:
        line_sum = sum((Decimal(str(i.amount)) for i in ex.line_items), Decimal("0"))
        mismatch = subtotal is not None and abs(line_sum - subtotal) > MONEY_TOL
        if mismatch:
            issues.append(
                Issue("line_items_vs_subtotal", "error",
                      f"line items sum to {line_sum}, subtotal says {subtotal}",
                      ("subtotal",))
            )
        for i in ex.line_items:
            expected = Decimal(str(i.unit_price)) * Decimal(str(i.quantity))
            if abs(expected - Decimal(str(i.amount))) > MONEY_TOL:
                issues.append(
                    Issue("line_item_arithmetic", "error",
                          f"{i.description!r}: {i.quantity} x {i.unit_price} != {i.amount}")
                )

    have_totals = None not in (subtotal, vat_amount, total)
    if have_totals and abs(subtotal + vat_amount - total) > MONEY_TOL:
        issues.append(
            Issue("total_reconciliation", "error",
                  f"{subtotal} + {vat_amount} != {total}",
                  ("subtotal", "vat_amount", "total"))
        )

    if subtotal is not None and vat_rate is not None and vat_amount is not None:
        expected = subtotal * vat_rate
        if abs(expected - vat_amount) > MONEY_TOL:
            issues.append(
                Issue("vat_rate_reconciliation", "error",
                      f"{subtotal} x {vat_rate} = {expected}, but vat_amount is {vat_amount}",
                      ("vat_rate", "vat_amount"))
            )

    if total is not None and total <= 0:
        issues.append(Issue("nonpositive_total", "error", f"total is {total}", ("total",)))

    # --- codes and dates --------------------------------------------------
    cur = f.get("currency")
    if cur is not None and cur not in ISO_CURRENCIES:
        issues.append(
            Issue("unknown_currency", "error",
                  f"{cur!r} is not a currency we settle in", ("currency",))
        )

    inv_d = _as_date(f.get("invoice_date"))
    due_d = _as_date(f.get("due_date"))
    if f.get("invoice_date") is not None and inv_d is None:
        issues.append(
            Issue("unparseable_date", "error",
                  "invoice_date is not a date", ("invoice_date",))
        )
    if inv_d and due_d and due_d < inv_d:
        issues.append(
            Issue("due_before_invoice", "error",
                  f"due {due_d} precedes invoice {inv_d}", ("due_date",))
        )
    if inv_d and inv_d > date(2027, 1, 1):
        issues.append(
            Issue("implausible_date", "warning",
                  f"invoice_date {inv_d} is in the far future", ("invoice_date",))
        )

    vat_no = f.get("supplier_vat")
    if vat_no is not None:
        s = str(vat_no).strip()
        if len(s) < 8 or not s[:2].isalpha() or not s[2:].replace(" ", "").isdigit():
            issues.append(
                Issue("vat_number_shape", "warning",
                      f"{vat_no!r} does not look like an EU VAT number", ("supplier_vat",))
            )

    return issues


def has_errors(issues: list[Issue]) -> bool:
    return any(i.severity == "error" for i in issues)
