# D1 — PCSK9 data feasibility: current evidence and unresolved work

Assessment date: 2026-10-16. This is an engineering evidence assessment, not credentialed assay approval.

## Decision

**Pause real-data training for the current direct PCSK9–LDLR IC50 endpoint.** Continue source verification and software work. Do not reverse the archived exclusions or reinterpret secretion/expression measurements as binding measurements to make a model train. No replacement target or endpoint has been selected.

The [23-row evidence register](../reviews/pcsk9-evidence-register.csv) preserves the earlier assay decisions and documents unresolved protocol fields. It links each assay to ChEMBL and records its original source-document ID. The earlier snapshot had 163 activity rows, according to the [14 October report](assay-review-2026-10-14.md), and zero approved measurements. Therefore the currently approved real set has **0 molecules, 0 active/inactive labels and 0 scaffolds**. Potential coverage and class balance cannot be reliably estimated from assay descriptions or the remaining abbreviated review CSV.

The original local raw snapshot and its database version were removed at the user's requested reset. The committed review and historical narrative remain. This assessment does not reconstruct missing original response bytes or claim a newly downloaded ChEMBL release. New acquisition must produce a new dated snapshot using the updated provenance workflow.

## Primary-source follow-up

| Source | What can currently be established | Remaining work |
|---|---|---|
| [Stapled peptide study, PMID 34266235](https://pubmed.ncbi.nlm.nih.gov/34266235/) | The indexed original-study abstract reports peptide binding and cellular uptake outcomes. It reports KD and EC50, which cannot be relabelled as our IC50 endpoint. | Read the full methods and supplementary activity tables; identify assay-specific IC50 data, species/constructs/controls and chemical identities; assess whether the peptide modality needs a separate specification. |
| [Cyclic tetramer publication, PMID 32944132](https://pubmed.ncbi.nlm.nih.gov/32944132/) | PubMed classifies this item as an editorial. It is a discovery lead to trace, not a primary assay protocol. | Locate the original patent/protocol and experimental tables before any approval. |
| [Cyclic peptide source, PMID 33356222](https://pubmed.ncbi.nlm.nih.gov/33356222/) | The earlier report identifies this source for follow-up; the current retrieval did not provide usable method detail. | Obtain the original paper/supplement and identify the exact endpoint. |
| [Diindolylmethane source, PMCID PMC6690802](https://pmc.ncbi.nlm.nih.gov/articles/PMC6690802/) | The prior review classified its PCSK9 protein readout as a different endpoint. Current browser retrieval encountered an access challenge. | Independently verify the original methods; retain exclusion from direct-binding pooling unless justified by separate experimental evidence. |

This register intentionally marks unknown species, constructs, methods and reuse terms as unknown. No inaccessible article was treated as read in full. Earlier review-sourced leads (CHEMBL4219125, CHEMBL4382228 and CHEMBL5233285) still require tracing to original experiments, as documented in the historical report.

## Requirements to resume

1. Acquire a complete target extract and record its provenance, or import a named bulk-release extract with original activity/assay fields.
2. Trace each proposed inclusion to its primary experimental method and activity table.
3. Record reviewer/date/source/species/constructs/method/conditions and rationale. Software records these claims; it does not verify a person's qualifications.
4. Decide which assay formats and molecular modalities are comparable before pooling.
5. Export the dataset audit and assess class counts, molecule/fingerprint duplicates, source overlap and scaffold diversity.
6. Freeze the development protocol and reserve suitable independent data before tuning where data permits.

Publication access or dataset availability does not establish redistribution rights. Reuse restrictions remain unassessed and must be resolved before a commercial dataset or hosted redistribution. Laboratory work and reviewer recruitment have not been performed or arranged.

## Status

Written feasibility recommendation and evidence register: delivered. Original-source verification, potential usable-coverage estimate and independent expert approval: **waiting on source access and qualified review**. D5 and real-data M2–M5 remain gated.
