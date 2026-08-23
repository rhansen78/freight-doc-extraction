# Evaluation methodology

## Why the corpus is synthetic

Real freight invoices cannot be published — they carry supplier terms, customer
identities and negotiated rates. A public evaluation set has to be generated.

That constraint turns out to be an advantage:

* **No labelling error floor.** The ground truth *is* the input to the renderer.
  A hand-labelled corpus disagrees with itself at some rate, and that rate sets
  a ceiling on the accuracy you can claim to measure.
* **Absence becomes measurable.** The generator records which fields it omitted
  from each rendering. Without that record, "the model invented this" is
  indistinguishable from "the model read something I missed" — so hallucination
  gets discussed anecdotally instead of measured.
* **Reproducibility.** Seed `20260823` regenerates the corpus byte-for-byte, so
  a change in the numbers is attributable to the extractor rather than to the
  data. `test_corpus_is_deterministic` enforces this.

The cost is honest and worth stating: synthetic documents are cleaner than real
ones. `scan_noise_v3` and the three-layout split narrow that gap; they do not
close it. Numbers here are an upper bound on production performance, and the
right use of the harness is to compare extractors and prompts against each
other, not to predict a production accuracy figure.

## Splits and threshold discipline

| split | documents | use |
|---|---|---|
| dev | 0–29 | choosing thresholds, iterating on prompts |
| held-out | 30–59 | reporting |

`CONFIDENCE_FLOOR` in `src/fde/policy.py` was chosen on dev and frozen before
held-out was scored. It sits in code with the date and the split it came from,
so changing it shows up in a diff.

This matters more than it looks. Tuning a threshold on the same data you report
is how an eval comes to describe a system that does not exist — the harness
reports a number, the number is real, and it does not survive contact with the
next thirty documents. The harness marks any dev-split report as optimistic in
its own output rather than trusting the reader to remember.

## Metrics, in priority order

**`escaped_defect_rate`** — of documents auto-posted, the fraction that were
wrong. The only metric with a direct cost attached. Everything else is a
diagnostic for it.

**`hallucination_rate`** — of fields genuinely absent from a document, how often
a value came back anyway.

**`absence_recall`** — of those absent fields, how often the extractor declared
them unresolved rather than dropping them silently.

**`field_accuracy`** — of fields present on the document, how many were read
correctly. Reported last and labelled "the flattering one", because an extractor
that invents plausible values scores well on it.

**`unnecessary_escalation_rate`** — of documents sent to review, how many were
actually fine. The cost side of the trade; a policy that escalates everything
has a perfect escaped-defect rate and no value.

## What this harness does not measure

* Document classification — every input is assumed to be a freight invoice.
* Multi-page documents and continuation pages.
* Real OCR. `scan_noise_v3` simulates character-level corruption; it does not
  simulate layout loss, skew, or table-structure collapse, which are the harder
  half of real scanned intake.
* Adversarial documents — prompt injection through document content is a real
  attack surface for any agentic intake pipeline and is out of scope here.
