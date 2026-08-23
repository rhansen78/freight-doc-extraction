from fde.policy import CONFIDENCE_FLOOR, decide
from fde.schema import CRITICAL_FIELDS, Extraction
from fde.validate import validate


def confident(**over):
    fields = {
        "invoice_number": "INV-1", "invoice_date": "2026-03-01",
        "supplier_name": "Nordfragt", "currency": "EUR", "total": "125.00",
    }
    fields.update(over)
    return Extraction(
        fields=fields, fields_unresolved=[],
        confidence={k: 0.99 for k in CRITICAL_FIELDS},
    )


def test_clean_confident_extraction_auto_posts():
    ex = confident()
    assert decide(ex, validate(ex)).auto_post


def test_low_confidence_escalates():
    ex = confident()
    ex.confidence["total"] = CONFIDENCE_FLOOR - 0.01
    assert decide(ex, validate(ex)).escalate


def test_validation_error_escalates():
    ex = confident(currency="XYZ")
    d = decide(ex, validate(ex))
    assert d.escalate and any(r.startswith("validation_error") for r in d.reasons)


def test_missing_critical_field_escalates():
    ex = confident()
    ex.fields["total"] = None
    ex.fields_unresolved = ["total"]
    assert decide(ex, validate(ex)).escalate
