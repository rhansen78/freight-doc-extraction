# Eval run — stub / heldout split

> **This run used the deterministic stub extractor.** The numbers below describe injected failure modes and demonstrate that the harness detects them. They are not a measurement of any model.

- corpus: 30 documents, seed `20260823`
- confidence floor: `0.75`

## What matters

| metric | value | reading |
|---|---:|---|
| **escaped defect rate** | 44.4% | wrong documents posted with no human review |
| **hallucination rate** | 29.5% | values returned for fields not on the document |
| absence recall | 70.5% | absent fields correctly declared unresolved |
| auto-post rate | 30.0% | documents needing no review |
| unnecessary escalation | 0.0% | reviews of documents that were actually fine |
| field accuracy | 89.4% | the flattering one |
| corpus defect rate | 83.3% | documents with any error |

## By layout

| layout | field accuracy |
|---|---:|
| `narrative_v2` | 93.2% |
| `scan_noise_v3` | 85.0% |
| `tabular_v1` | 89.7% |

## Cost and latency

- p50 latency: 922 ms
- p95 latency: 1302 ms
- cost: not computed (set FDE_PRICE_IN_PER_MTOK / FDE_PRICE_OUT_PER_MTOK to price a run)
