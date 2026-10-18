# Local research workflow market review

Reviewed 18 October 2026. This is a focused comparison of documented research
workflows, not an exhaustive inventory of vendors or a claim that PCSK9 Lab has
equivalent scientific or enterprise readiness. Vendor pages can change.

| Program and documented workflow | PCSK9 Lab before this change | Decision |
|---|---|---|
| [CDD Vault structure search](https://support.collaborativedrug.com/hc/en-us/articles/360044466812-Structure-Searching-in-CDD-Vault) offers exact, substructure and Tanimoto similarity search. [Collection scoping](https://support.collaborativedrug.com/hc/en-us/articles/214358483-Search-by-compound-collection) narrows searches. | Collections stored standardized structures, but only listed every row. | Add these three read-only search modes across the selected project's saved collections. Preserve entry and collection identifiers and export displayed results. |
| [CDD Vault saved searches](https://support.collaborativedrug.com/hc/en-us/articles/214358583-Saved-Search) retain query criteria and report options for later reruns. | No saved query records. | Defer until a concrete repeat-search workflow justifies additive storage and versioned query semantics. |
| [DataWarrior chemistry documentation](https://openmolecules.org/help/chemistry.html) describes substructure and similarity filtering using molecular descriptors. | RDKit profiles, fingerprints and comparison views existed. | Reuse the application's existing Morgan representation; label similarity as structural only. |
| [Benchling warehouse documentation](https://docs.benchling.com/docs/getting-started) connects registered entities, assay results and reporting. | Projects, collections, immutable dataset versions, assay review, predictions and reports existed as separate local workflows. | Keep source and assay attribution; do not conflate collection membership or a structure hit with measured activity. |
| [KNIME data apps](https://docs.knime.com/work/deployments/data-apps) expose widgets, tables and downloads around workflows. | Streamlit already exposed local forms, tables, CSV export and batch jobs. | Extend the existing Projects & history screen instead of adding a deployment system. |

## Delivered in this pass

`GET /collections/search` performs project-scoped exact, substructure or similarity
search over saved collection molecules. It returns counts, provenance IDs,
standardized query and up to the requested result limit. Similarity uses Morgan
radius-2, 2048-bit Tanimoto, with a user-selected minimum. The Streamlit page
supports all three modes, one-collection scope and CSV of displayed hits.

This is workflow parity for a narrow, local search operation. It does not add a
structure sketcher, saved searches, chemical property filters, assay joins,
multi-user sharing, or molecular prediction evidence. Those would require their
own use cases and validation. A structural match alone is no evidence of PCSK9
activity, safety, or clinical suitability.
