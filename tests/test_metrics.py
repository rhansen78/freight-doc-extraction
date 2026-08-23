"""The harness has to detect each failure mode. These tests are the proof."""
from fde.extract import StubExtractor
from fde.generate import build_corpus
from fde.policy import decide
from fde.validate import validate
from metrics import score_document, summarise


def run(extractor, n=30):
    docs = build_corpus(n=n)
    scores, esc, exs = [], [], []
    for d in docs:
        ex = extractor.extract(d)
        exs.append(ex)
        esc.append(decide(ex, validate(ex)).escalate)
        scores.append(score_document(d, ex))
    return summarise(scores, esc, exs)


def test_perfect_extractor_scores_perfectly():
    s = run(StubExtractor(wrong_rate=0.0, hallucinate_rate=0.0, silent_null_rate=0.0))
    assert s.field_accuracy == 1.0
    assert s.hallucination_rate == 0.0
    assert s.absence_recall == 1.0
    assert s.escaped_defect_rate == 0.0
    assert s.defect_rate == 0.0


def test_hallucination_is_detected():
    s = run(StubExtractor(wrong_rate=0.0, hallucinate_rate=1.0, silent_null_rate=0.0))
    assert s.hallucination_rate == 1.0
    assert s.absence_recall == 0.0


def test_wrong_values_lower_accuracy():
    clean = run(StubExtractor(wrong_rate=0.0, hallucinate_rate=0.0, silent_null_rate=0.0))
    dirty = run(StubExtractor(wrong_rate=0.5, hallucinate_rate=0.0, silent_null_rate=0.0))
    assert dirty.field_accuracy < clean.field_accuracy


def test_field_accuracy_can_hide_hallucination():
    """The central claim of this repo, asserted as a test.

    An extractor that reads every present field correctly and invents a value
    for every absent one scores 100% field accuracy while being unusable.
    """
    s = run(StubExtractor(wrong_rate=0.0, hallucinate_rate=1.0, silent_null_rate=0.0))
    assert s.field_accuracy == 1.0
    assert s.defect_rate > 0.5


def test_escaped_defects_never_exceed_defects():
    s = run(StubExtractor(seed=3))
    assert 0.0 <= s.escaped_defect_rate <= 1.0
    assert s.auto_post_rate + s.escalation_rate == 1.0
