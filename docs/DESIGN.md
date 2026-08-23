# Design notes

Decisions worth arguing about, and what the alternative would have cost.

## 1. The model reads; Python judges

**Decision.** The extractor returns values. It is never asked whether those
values are consistent. All arithmetic, code and date checks live in
`validate.py`, which imports no model client and is tested independently.

**Alternative considered.** Ask the model to self-check — "verify this invoice
reconciles" — or run a second model call as a critic.

**Why not.** A model asked to confirm its own output tends to confirm it, and a
critic call doubles cost and latency to re-derive something `Decimal` arithmetic
answers exactly. Self-checking is worth reaching for when correctness is a
judgement (is this description of the service accurate?), not when it is a
calculation. Here it is a calculation.

**Consequence.** Validation is free, deterministic and auditable — an operator
can be shown the rule that fired. The trade is that validation only catches
*inconsistency*. An invoice where every field is misread but the arithmetic
happens to reconcile passes cleanly. That gap is why confidence and the
hallucination probe exist alongside it.

## 2. Null is a first-class answer

**Decision.** A field not printed on the document must come back `null` and be
named in `fields_unresolved`. A null that was not declared raises `silent_null`.

**Alternative considered.** Let absent fields be omitted from the payload
entirely.

**Why not.** Downstream, an omitted key and a key the extractor failed on are
the same thing, and they need different handling — one is a sparse document, the
other is a bug. Forcing an explicit declaration makes the extractor state its
own coverage, and makes the difference testable.

**Consequence.** The prompt spends its most emphatic instruction on this rather
than on formatting. The escalation policy can then treat "three optional fields
missing" as a sparse document rather than a failure, which is what keeps the
auto-post rate from collapsing on thin invoices.

## 3. Ground truth first, document second

**Decision.** `generate.py` builds a `FreightInvoice`, then `render.py` produces
text from it, omitting a recorded subset of fields.

**Alternative considered.** Collect real documents and label them.

**Why not.** Beyond the obvious — real freight invoices are confidential — a
labelled corpus cannot answer the question this repo is built around. To measure
invention you must know what was *not* on the page, and a labeller only records
what was.

**Consequence.** Two safeguards were needed to keep the probe honest, both found
by tests rather than by inspection:

* a field whose value still appears elsewhere in the rendered text is removed
  from the absent set, or the extractor gets blamed for reading something that
  was genuinely there;
* a zero VAT rate is never omitted, because a document showing `0.00` VAT lets a
  reader infer the rate legitimately. Returning `0` there is reasoning, not
  invention, and scoring it as a hallucination would make the metric dishonest
  in the extractor's disfavour.

Both are enforced in `test_absent_fields_are_really_absent_from_the_text`.

## 4. Confidence is asked for, not inferred

**Decision.** The model returns a per-field confidence, and the policy gates on
the minimum across critical fields.

**Alternative considered.** Derive confidence from logprobs, or drop it and gate
only on validation.

**Why not.** Logprobs are not exposed by every provider and do not survive a
tool-call boundary cleanly. Gating on validation alone misses the case that
matters most on `scan_noise_v3`: a value reconstructed from a damaged string,
which reconciles arithmetically and is still wrong.

**Consequence.** Self-reported confidence is weakly calibrated and should be
treated as a coarse signal, not a probability. It is used as one escalation
trigger among four, never alone. Calibrating it — reliability curves against
observed error — is the obvious next piece of work and is not done here.

## 5. Three layouts, not one

**Decision.** `tabular_v1`, `narrative_v2`, `scan_noise_v3`, with different
label wording and field order, scored separately as well as together.

**Why.** A single template measures how well an extractor learned that template.
The per-layout breakdown is diagnostic: a large gap between tabular and
narrative means the extractor is matching labels rather than reading, and that
gap predicts what happens when a new supplier joins.

## Known limitations

* Self-reported confidence is uncalibrated (see 4).
* Single-page documents only; no continuation-page handling.
* `scan_noise_v3` simulates character corruption, not layout collapse — the
  harder half of real scanned intake.
* No defence against prompt injection via document content. For a pipeline that
  ingests documents from outside parties this is a real attack surface, and
  addressing it properly means treating document text as untrusted throughout,
  not adding a filter.
* The corpus is drawn from fixed word lists, so lexical diversity is far below
  a real supplier population.
