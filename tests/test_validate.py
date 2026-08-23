from fde.schema import Extraction, LineItem
from fde.validate import has_errors, validate


def good() -> Extraction:
    return Extraction(
        fields={
            "invoice_number": "INV-1", "invoice_date": "2026-03-01",
            "supplier_name": "Nordfragt Logistik A/S", "currency": "EUR",
            "subtotal": "100.00", "vat_rate": "0.25", "vat_amount": "25.00",
            "total": "125.00", "due_date": "2026-03-31",
        },
        fields_unresolved=[],
        confidence={k: 0.95 for k in
                    ("invoice_number", "invoice_date", "supplier_name", "currency", "total")},
        line_items=[LineItem(description="Road freight", quantity=2,
                             unit_price="50.00", amount="100.00")],
    )


def test_clean_extraction_has_no_errors():
    assert not has_errors(validate(good()))


def test_detects_total_mismatch():
    ex = good()
    ex.fields["total"] = "130.00"
    assert "total_reconciliation" in {i.rule for i in validate(ex)}


def test_detects_vat_rate_mismatch():
    ex = good()
    ex.fields["vat_rate"] = "0.19"
    assert "vat_rate_reconciliation" in {i.rule for i in validate(ex)}


def test_detects_line_item_sum_mismatch():
    ex = good()
    ex.line_items = [LineItem(description="x", quantity=1, unit_price="7.00", amount="7.00")]
    assert "line_items_vs_subtotal" in {i.rule for i in validate(ex)}


def test_detects_silent_null():
    """A null that was not declared unresolved is the contract violation."""
    ex = good()
    ex.fields["due_date"] = None
    assert "silent_null" in {i.rule for i in validate(ex)}


def test_declared_null_is_not_a_silent_null():
    ex = good()
    ex.fields["due_date"] = None
    ex.fields_unresolved = ["due_date"]
    assert "silent_null" not in {i.rule for i in validate(ex)}


def test_detects_missing_critical_field():
    ex = good()
    ex.fields["invoice_number"] = None
    ex.fields_unresolved = ["invoice_number"]
    assert "critical_field_missing" in {i.rule for i in validate(ex)}


def test_detects_unknown_currency():
    ex = good()
    ex.fields["currency"] = "XYZ"
    assert "unknown_currency" in {i.rule for i in validate(ex)}


def test_detects_due_before_invoice():
    ex = good()
    ex.fields["due_date"] = "2026-02-01"
    assert "due_before_invoice" in {i.rule for i in validate(ex)}


def test_rounding_within_tolerance_is_accepted():
    ex = good()
    ex.fields["total"] = "125.01"
    assert not has_errors(validate(ex))
