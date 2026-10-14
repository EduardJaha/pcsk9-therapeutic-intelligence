# PCSK9 ChEMBL assay desk review — 14 October 2026

## Decision

**0 of 23 assays approved** for the version 1 endpoint, direct inhibition of PCSK9 binding to LDLR. The 163 activity rows in the saved snapshot therefore do not form a real training set. The detailed, machine-readable decision for every assay is in [`reviews/pcsk9-assay-review-2026-10-14.csv`](../reviews/pcsk9-assay-review-2026-10-14.csv). Each row is marked `exclude` from this narrowly defined dataset, with a specific reason. This does not assert that the underlying experiments are invalid or that PCSK9 cannot be targeted through other mechanisms.

This is a conservative **document-based screen**, not independent laboratory verification or credentialed expert sign-off. It used the ChEMBL assay descriptions, target relationship and confidence fields, the linked ChEMBL source documents, and available original publications. A scientist can revisit the deferred direct-binding descriptions by tracing their original experiments. No therapeutic claim or model training follows from this review.

Snapshot: `data/pcsk9-chembl-2026-10-14.json` (local, Git-ignored), SHA-256 `be3e92688173485851564e9d800b4cf1079b3ff4851f0963117621a9abda162f`. Query: ChEMBL `CHEMBL2929`, standardized exact IC50 in nM with pChEMBL present; 163 activities and 23 assay IDs appeared. The snapshot file and full assay descriptions remain local.

## Why the records did not qualify

| Reason | Assays | Activity rows | Examples |
|---|---:|---:|---|
| Indirect target assignment and a secretion/translation readout | 2 | 60 | [CHEMBL3887820](https://www.ebi.ac.uk/chembl/assay_report_card/CHEMBL3887820/), [CHEMBL3887821](https://www.ebi.ac.uk/chembl/assay_report_card/CHEMBL3887821/) |
| Direct binding suggested, but ChEMBL cites a review or editorial instead of the original assay; some are also ambiguous | 12 | 25 | [CHEMBL4221944](https://www.ebi.ac.uk/chembl/assay_report_card/CHEMBL4221944/), [CHEMBL4383962](https://www.ebi.ac.uk/chembl/assay_report_card/CHEMBL4383962/), [CHEMBL5236434](https://www.ebi.ac.uk/chembl/assay_report_card/CHEMBL5236434/) |
| Cellular PCSK9 amount, translation, transcription, or reporter readout | 7 | 75 | [CHEMBL4434276](https://www.ebi.ac.uk/chembl/assay_report_card/CHEMBL4434276/), [CHEMBL5333523](https://www.ebi.ac.uk/chembl/assay_report_card/CHEMBL5333523/) |
| Different binding partner or unspecified readout | 2 | 3 | [CHEMBL5038682](https://www.ebi.ac.uk/chembl/assay_report_card/CHEMBL5038682/), [CHEMBL5040279](https://www.ebi.ac.uk/chembl/assay_report_card/CHEMBL5040279/) |

The category counts include every assay exactly once; some assays have more than one concern. The activity-level quality screen separately flags four potential duplicate rows. ChEMBL defines its assay type and target confidence fields as curation metadata, so a `B` assay and a direct target assignment alone do not prove a PCSK9–LDLR interaction readout. See [ChEMBL's assay and activity guidance](https://chembl.gitbook.io/chembl-interface-documentation/frequently-asked-questions/chembl-data-questions) and [target relationship definitions](https://chembl.gitbook.io/chembl-interface-documentation/frequently-asked-questions/target-questions).

## Source checks that affected decisions

- The records for [CHEMBL4221943/44/46](https://www.ebi.ac.uk/chembl/document_report_card/CHEMBL4219125/) point to a [literature and patent overview](https://pubmed.ncbi.nlm.nih.gov/29519739/). CHEMBL4221944 describes a relevant recombinant PCSK9–LDLR SPR experiment, but the current record does not identify the original experiment well enough to check its constructs, controls, and measurement independently.
- [CHEMBL4383959/62/71](https://www.ebi.ac.uk/chembl/document_report_card/CHEMBL4382228/) point to a [review of small-molecule PCSK9 inhibitors](https://pubmed.ncbi.nlm.nih.gov/30448414/). CHEMBL4383962 and CHEMBL4383971 describe LDLR-AB fragments with unknown protein origins; they need original-source verification and may require a separate endpoint group.
- [CHEMBL5236415/19/32/33/34](https://www.ebi.ac.uk/chembl/document_report_card/CHEMBL5233285/) point to a [review article](https://pubmed.ncbi.nlm.nih.gov/36446632/). CHEMBL5236434 explicitly mentions LDLR, but its original assay and controls need to be traced before inclusion.
- [CHEMBL4622704](https://www.ebi.ac.uk/chembl/assay_report_card/CHEMBL4622704/) points to an [editorial patent highlight](https://pubmed.ncbi.nlm.nih.gov/32944132/). The ChEMBL assay description does not name the TR-FRET binding partner. The underlying patent may describe a PCSK9–LDLR assay, but the current activity record is insufficient to merge with a verified direct-binding dataset.
- The original [diindolylmethane study](https://pmc.ncbi.nlm.nih.gov/articles/PMC6690802/) explains that its HepG2 readout is reduced PCSK9 protein; those IC50s are a different endpoint. The [cyclic peptide study](https://pubmed.ncbi.nlm.nih.gov/33356222/) and the [stapled peptide study](https://pubmed.ncbi.nlm.nih.gov/34266235/) investigate PCSK9-targeting peptides, but their ChEMBL assays in this snapshot do not unambiguously measure inhibition of full PCSK9–LDLR binding.

## What would change the decision

Trace the original papers or patents behind the three review-sourced direct-binding candidates (CHEMBL4221944, CHEMBL4383962/71, CHEMBL5236434). Obtain primary assay protocols and activity tables, verify compound identity and duplicate status, and decide whether full LDLR, LDLR fragments, cellular surface binding, SPR, ELISA, and TR-FRET measurements can be pooled. If they cannot, create separate endpoint groups. The current snapshot is too small and mixed to justify weakening the endpoint rule merely to make the model train.

An independent PCSK9 assay specialist should inspect these decisions before a real-data model is interpreted. The software continues to permit the synthetic fixture for functional testing only.
