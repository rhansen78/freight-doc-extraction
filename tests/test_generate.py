"""The corpus must be reproducible and internally consistent, or no eval built
on it means anything."""
from decimal import Decimal

from fde.generate import build_corpus
from fde.schema import CRITICAL_FIELDS


def test_corpus_is_deterministic():
    a = build_corpus(n=12, seed=1234)
    b = build_corpus(n=12, seed=1234)
    assert [d.text for d in a] == [d.text for d in b]
    assert [d.absent_fields for d in a] == [d.absent_fields for d in b]


def test_different_seeds_differ():
    a = build_corpus(n=8, seed=1)
    b = build_corpus(n=8, seed=2)
    assert [d.text for d in a] != [d.text for d in b]


def test_ground_truth_arithmetic_reconciles():
    for d in build_corpus(n=40):
        t = d.truth
        assert sum(i.amount for i in t.line_items) == t.subtotal
        assert t.subtotal + t.vat_amount == t.total
        for i in t.line_items:
            assert abs(i.unit_price * i.quantity - i.amount) <= Decimal("0.01")


def test_critical_fields_are_never_omitted():
    for d in build_corpus(n=40):
        assert not set(d.absent_fields) & set(CRITICAL_FIELDS)


def test_absent_fields_are_really_absent_from_the_text():
    """The hallucination probe is only valid if omission actually happened."""
    for d in build_corpus(n=40):
        for name in d.absent_fields:
            val = getattr(d.truth, name, None)
            if val is None:
                continue
            assert str(val) not in d.text, f"{d.doc_id}: {name} still printed"


def test_all_layouts_are_exercised():
    assert len({d.layout for d in build_corpus(n=12)}) == 3
