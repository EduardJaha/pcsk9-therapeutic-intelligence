# Local assistant evaluation — 28 October 2026

The broader campaign checks handling of explicitly selected evidence using the
same structured-output constraints as the application. It is a software behavior
experiment on generated, fictional records. It does not establish scientific
accuracy, clinical suitability or performance on real publications.

## Frozen data and training

`scripts/assistant_curriculum.py` creates six tasks: values/units/endpoint
extraction, comparing incompatible endpoints without pooling, conflicting
reports, missing evidence, a short research report and malicious instructions
embedded in evidence. Distractor passages, source identifiers and ordering vary.
All generated measurements are explicitly synthetic and remain in ignored
`data/assistant-training/`; they are never imported into the research database.

The campaign freezes 224 training examples (192 evidence tasks and 32
documentation replay examples), 48 validation examples and 48 final-test
examples. Scenario groups, identifiers and question wording are separated.
Shared generator templates remain a source of dependence between partitions;
the test is held out from selection but is not an independent biomedical test.
Checksums, exact assignments, source snapshots and original responses are kept.

Two Qwen3 1.7B QLoRA candidates were trained on the cached NF4 base: a fresh
adapter and a continuation of the earlier documentation adapter. Rank is 16,
alpha 32, batch size 1 with accumulation 8 and context length 2,048. Each final
candidate completed two epochs/56 optimizer updates. The fresh learning rate
was 0.0001; the continuation rate was 0.00005 with a fresh optimizer/schedule.
Only assistant answer tokens contribute to loss. Unsloth runs separately from
the application's locked environment. No foundation model was trained from
scratch. Answering in the app does not perform training.

## Selection protocol and limitations

The first broader campaign (`2026-10-27-evidence-v3`) found little improvement.
A validation-only diagnostic showed that teacher answers serialized statement
keys first while Ollama's constrained schema generated citation keys first.
The v4 amendment sorted training-answer JSON keys to match production ordering
and prescribed two epochs before any final-test evaluation. Dataset bytes and
partitions were preserved. These are sequential development experiments, not
multiple independent confirmations.

Every benchmark uses the production system prompt and JSON schema, temperature
0, seed 42, thinking disabled, context 8,192 and output limit 1,000 tokens.
Gold answers are never sent in generation requests. The same cached base was
dequantized and exported without an adapter as the causal baseline. Trained
exports use Q8_0. The separately installed `qwen3:4b-instruct` (Q4_K_M) is a
practical larger-model reference with different size and quantization; it was
not fine-tuned in this campaign.

Mechanical checks require valid schema/citations, expected source coverage,
required facts, no added numbers, appropriate evidence gaps and no role or
clinical overclaims. Citation existence does not prove entailment. Conservative
required-phrase checks can reject valid paraphrases; passing can also miss an
unsupported interpretation. Model outputs still need human review.

A scorer defect on validation treated "fictional" and "simulated" differently
from "synthetic" when checking origin labels. A narrow clarification was frozen
before final candidate outputs and final-test evaluation. It normalizes those
origin words only. Numeric, unit, citation, completeness and abstention checks
are unchanged. Original literal scores and raw outputs remain intact alongside
the additive corrected score views used for selection.

Selection uses validation only: highest task pass count without regression on
the missing-evidence task; retain the incumbent on a tie, then prefer a smaller
trained candidate and lower validation loss. The selected model and all input
hashes are locked before evaluating the final test once against the base and
incumbent. Promotion additionally requires application regression checks and a
final-test result at least equal to the incumbent. A failed promotion does not
authorize choosing another model using final-test outputs.

Real biomedical source leads remain outside training. Appropriate source,
assay, endpoint, modality, reuse-rights and expert review are still required.
LLM training cannot approve assays or provide measurements for molecular models.

## Results and deployment decision

Counts below use the frozen origin-word clarification. Each partition contains
eight cases per task (48 total); these counts are not scientific accuracy.

| Model | Validation passes | Reserved test passes |
|---|---:|---:|
| Cached 1.7B base, exported without adapter | 3/48 | 4/48 |
| Current documentation-trained 1.7B assistant | 16/48 | 23/48 |
| Fresh 1.7B evidence adapter, two epochs | 18/48 | Not run |
| Continued 1.7B evidence adapter, two epochs | 22/48 | Not run |
| Installed 4B reference, selected on validation | 24/48 | 16/48 |

The 4B reference won validation and was locked before the final comparison.
It failed the promotion rule on the reserved test: 16 passes versus the current
assistant's 23. The application therefore retains
`pcsk9-assistant:continued-20261027-02`. The fresh and continued evidence adapters
were not selected and were not tried on the final test. No further tuning or
alternative model selection was performed using these test outcomes.

The retained model's final-test breakdown is extraction 8/8, missing evidence
8/8, adversarial excerpts 7/8, comparison 0/8, conflict 0/8 and report 0/8.
The selected 4B reference scored extraction 0/8, missing evidence 8/8,
adversarial excerpts 0/8, comparison 2/8, conflict 0/8 and report 6/8. These
different weaknesses make the total an incomplete description. Neither model
has demonstrated reliable general research reasoning. Original literal scores
for the 4B reference were 19/48 validation and 12/48 test; the correction accounts
for the remaining passes. Other models' aggregate counts were unchanged.

Fresh and continued canonical validation losses decreased to 0.26046464 and
0.17058067 respectively. Lower loss did not establish a deployment improvement.
Future model development needs newly frozen evaluation cases; the final-test
outputs above have now been observed and cannot be reused as untouched evidence.

## Local artifacts

The complete campaign is under
`data/assistant-training/2026-10-28-evidence-v4/`. Inspect `protocol.json`,
`scoring-clarification.json`, `selection.json`, `benchmarks/`, `scores/`,
candidate `run.json` files, and the final campaign report. The earlier pilot,
continuation and v3 campaign remain preserved in their own directories.
