# freight-doc-extraction

[![ci](https://github.com/rhansen78/freight-doc-extraction/actions/workflows/ci.yml/badge.svg)](https://github.com/rhansen78/freight-doc-extraction/actions/workflows/ci.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Agentic extraction of structured data from freight invoices, with an evaluation
harness that measures the thing that actually matters: **how often a wrong
document gets posted without anyone looking at it.**

The extraction is the easy half. Any capable model reads an invoice. The
engineering is in knowing when it was wrong.

---

## The problem with field accuracy

Two extractors, same 30 held-out documents, real numbers from this harness:

| | extractor A | extractor B |
|---|---:|---:|
| field accuracy | **100.0%** | 92.8% |
| hallucination rate | 100.0% | **0.0%** |
| auto-post rate | 80.0% | 53.3% |
| **escaped defect rate** | **70.8%** | **25.0%** |

Extractor A reads every printed field correctly and *invents* a plausible value
for every field that is not on the document. It has perfect field accuracy, the
highest auto-post rate, and it is unusable: seven of every ten documents it
posts unattended are wrong, and you cannot tell its readings from its
inventions.

Extractor B misreads about one field in fourteen and never invents. It looks
worse on the metric most extraction projects report, and it is the one you
would ship.

<sub>Reproduce with `python evals/ab_demo.py`, or see
`test_field_accuracy_can_hide_hallucination`. Both columns are the stub with
different injected failure modes — see the note under Results.</sub>

This is not a hypothetical, and not only a property of a rigged stub. It is
asserted as a test (`test_field_accuracy_can_hide_hallucination` in
`tests/test_metrics.py`), and it showed up on the first real measurement:
`claude-sonnet-4-5` reads **99.5%** of printed fields correctly on the held-out
split and still posts **14.3%** of its unattended documents wrong. See
[Results](#results).

Measuring it requires knowing which fields were genuinely absent from each
document. That is knowable here because the corpus is **generated from ground
truth rather than labelled after the fact**: the data comes first, the document
is rendered from it, and the generator records what it deliberately omitted.

---

## Architecture

```
                 ┌──────────────┐
   document ───► │  extractor   │  model reads; returns values or null
                 └──────┬───────┘
                        │  never computes, never infers
                 ┌──────▼───────┐
                 │  validator   │  Python checks arithmetic and codes
                 └──────┬───────┘     (no model involved)
                        │
                 ┌──────▼───────┐
                 │   policy     │  escalate, or post unattended
                 └──────┬───────┘
                        │
              auto-post ◄┴► human review
```

Three decisions worth defending:

**The model never checks its own arithmetic.** Asked "does this invoice add
up?", a language model will usually say yes — agreement is the cheaper token
path. Python asked the same question is right every time, costs nothing, and
its answer is auditable. So the model reads and the validator judges, and they
are separate files with separate tests.

**A null is a correct answer; an invented value is a defect.** The extraction
contract requires that a field not printed on the document comes back `null`
*and* is named in `fields_unresolved`. A null that was not declared is itself a
validation error (`silent_null`) — dropping a field quietly is the one behaviour
the pipeline will not tolerate, because it is indistinguishable downstream from
a field that was never there.

**Escalation is a business decision, reported as two numbers.** A system can
post 95% of documents unattended with 0.5% escaped defects, or post 60% with
none. Which is better depends on the cost of a wrong posting versus the cost of
a review. The harness reports auto-post rate and escaped defect rate separately
rather than collapsing them into a single score that hides the trade.

---

## Results

Held-out split (documents 30–59), `claude-sonnet-4-5`, August 2026.

| metric | value |
|---|---:|
| field accuracy | 99.5% |
| hallucination rate | 4.5% |
| absence recall | 95.5% |
| auto-post rate | 93.3% |
| **escaped defect rate** | **14.3%** |
| unnecessary escalation | 100% |
| corpus defect rate | 13.3% |

By layout: `tabular_v1` 100.0%, `narrative_v2` 100.0%, `scan_noise_v3` 98.4%.
Latency p50 6.7 s, p95 9.4 s.

**Read the first and fifth rows together.** The model reads 99.5% of printed
fields correctly, and one in seven of the documents it posts without review is
still wrong. That is the argument at the top of this page, measured on a real
model rather than asserted with a stub.

### What the first real run found

The harness was pointed at a real model twice. Both runs found something, and
neither finding was the one expected.

**Run 1 — the specification was wrong, not the model.** 14 of 17 field errors
landed on `vat_rate`, every one firing `vat_rate_reconciliation`. The document
prints "VAT @ 25%", the model returned `25`, ground truth held `0.25`, and
nothing in the prompt or the tool schema said which form was wanted. That is an
underspecified contract, not a misread. Fixed in the contract — units are now
stated in the system prompt and carried as per-field descriptions in the tool
schema, where the model actually reads them.

**Run 2 — fixing the contract improved every headline number and made the
system less safe.**

| | run 1 (ambiguous spec) | run 2 (spec fixed) |
|---|---:|---:|
| field accuracy | 95.5% | 99.5% |
| auto-post rate | 50.0% | 93.3% |
| corpus defect rate | 50.0% | 13.3% |
| **escaped defect rate** | 6.7% | **14.3%** |
| hallucination rate | 0.0% | **4.5%** |
| unnecessary escalation | 6.7% | **100%** |

All four defective documents were auto-posted; none were caught. Both escalated
documents were clean. Across 30 documents exactly one validation rule fired, and
only as a warning.

The escalation policy had not been detecting defects. `vat_rate_reconciliation`
fired on 14 documents that were defective *because of the same ambiguity that
made the rule fire* — the discrimination was an artefact of the bug. Remove the
bug and no signal remains.

What survives is exactly what deterministic validation cannot reach:

- `doc_0031`, `doc_0043` — the model invented a `vat_rate` for documents that
  printed none. Internally consistent, so every arithmetic rule passes.
- `doc_0038` — `supplier_vat` misread under OCR noise. `vat_number_shape`
  noticed, but it is a warning and does not escalate.
- `doc_0059` — `customer_name` misread. Free text, nothing to reconcile against.

Confidence gating caught none of them. The model was confident and wrong.

### What this says to do next

Stated rather than done, because these numbers are the held-out split:

1. Promote `vat_number_shape` from warning to error, which would catch
   `doc_0038`.
2. Add a cheap absence check — re-ask, cheaply and in isolation, whether a
   field the model returned actually appears on the page. Invention is the
   dominant residual failure and no arithmetic rule can see it.
3. Calibrate confidence against observed error instead of trusting it raw.

Tuning any of these against the table above and then republishing it would be
threshold-fitting on the reporting split — the failure `docs/EVAL.md` exists to
prevent. The legitimate route is to change them on the dev split and re-run
held-out once.

### Harness validation — stub extractor

The stub is a deterministic fake with **injected** failure modes. These numbers
show the harness detects those failures. **They measure no model.**

| metric | value |
|---|---:|
| escaped defect rate | 44.4% |
| hallucination rate | 29.5% |
| absence recall | 70.5% |
| auto-post rate | 30.0% |
| unnecessary escalation | 0.0% |
| field accuracy | 89.4% |


## Running it

```bash
make install          # pip install -e ".[dev,claude,mcp]"
make test             # 25 tests, no API key, no network
make eval             # stub extractor over the held-out split
make corpus           # print a sample generated document

export ANTHROPIC_API_KEY=...
make eval-real        # the real measurement
```

CI runs the tests and the stub eval on every push. Neither needs a key.

---

## MCP server

```bash
fde-mcp               # stdio
```

| tool | purpose |
|---|---|
| `extract_document` | text → fields + validation issues + escalation decision |
| `validate_fields` | run the deterministic rules over any payload; no model |
| `sample_document` | one corpus document with its ground truth and omissions |

`extract_document` deliberately does not return a bare dictionary of values. It
returns `escalate` in the same payload, so a calling agent can distinguish
"here is the data" from "here is data you should not act on". An endpoint that
returned only the fields would leave that to the caller to guess.

---

## Layout

```
src/fde/
  schema.py      typed invoice + extraction envelope; CRITICAL_FIELDS
  generate.py    synthetic corpus, ground truth first, seeded
  render.py      three layouts + OCR-style corruption
  extract.py     ClaudeExtractor (real) and StubExtractor (CI)
  validate.py    deterministic rules; calls no model
  policy.py      escalation decision; frozen confidence threshold
  mcp_server.py  MCP tools
evals/
  metrics.py     scoring, ordered by how much anyone should care
  harness.py     runner, dev/held-out splits, markdown report
docs/
  DESIGN.md      the trade-offs, argued
  EVAL.md        methodology and threshold discipline
```

## On the data

Every supplier, customer, rate and document in this repository is invented by
`generate.py` from fixed word lists. There is no real invoice here, no real
company, and nothing derived from any employer's system.


---

## License

MIT — see [LICENSE](LICENSE).
