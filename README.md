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

This is not a hypothetical. It is asserted as a test — `test_field_accuracy_can_hide_hallucination`
in `tests/test_metrics.py` — because it is the failure mode that survives an
extraction project's demo and shows up three months into production.

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

### Held-out split — stub extractor

The stub is a deterministic fake with **injected** failure modes. These numbers
demonstrate that the harness detects those failures. **They measure no model.**

| metric | value |
|---|---:|
| escaped defect rate | 44.4% |
| hallucination rate | 29.5% |
| absence recall | 70.5% |
| auto-post rate | 30.0% |
| unnecessary escalation | 0.0% |
| field accuracy | 89.4% |

Note the gap between the last row and the first: 89% field accuracy, and nearly
half of the unattended postings wrong. That gap is the entire argument
of this repository.

### Held-out split — real model

_Not yet run. `make eval-real` fills this in; the table stays empty until it
does rather than carrying a number nobody measured._

| metric | value |
|---|---:|
| escaped defect rate | — |
| hallucination rate | — |
| absence recall | — |
| auto-post rate | — |
| field accuracy | — |

---

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
