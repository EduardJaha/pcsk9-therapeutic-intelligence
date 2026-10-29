# Literature evidence workflow

Open **Assays & evidence → Literature evidence**. This workflow retrieves public
publications, preserves source bytes, extracts methods/tables, and stores local
LLM assay drafts. It does not approve assays, change measurements, pool endpoints,
or feed training. Existing ChEMBL curation and qualified-review gates remain.

## Retrieval and accessible full text

Enter shared search keywords and explicit publication dates. Searches query
PubMed eSearch/eFetch and Europe PMC core metadata, retaining provider-specific
date parameters, totals, caps, failures, retrieval time, exact response logs and
SHA-256 hashes. At most 50 results per provider are fetched per search. This is a
bounded discovery tool, not an exhaustive/systematic literature review. Refine
queries to resolve capped results. PubMed IDs are read from the publication's
own identifier list, never its references. Cross-provider duplicates share
PMID/PMCID/DOI matches and retain their original provider metadata.

Select a result and retrieve repository XML, PDF, or explicitly choose its
abstract. Europe PMC JATS supplies section/table/footnote locators. NLM eFetch
can supply repository XML when Europe PMC is unavailable. XML containing only
an abstract is explicitly marked `abstract_only`. Missing full text is a gap.
PDF retrieval supports same-origin repository redirects and NLM's current
anonymous public PMC dataset. It requires an unambiguous deposited version,
retains its metadata/license/retraction indicator and verifies supplied MD5
file checksums as well as application SHA-256 hashes. The legacy OA/FTP service
was retired in August 2026 and is not used. These are free public file reads;
no cloud infrastructure/account is provisioned. See [NLM's current distribution
documentation](https://pmc.ncbi.nlm.nih.gov/tools/pmcaws/) and [dataset README](https://pmc-oa-opendata.s3.amazonaws.com/README.txt).

Where repository retrieval fails, upload a legally accessible PDF associated
with a retained publication and record its source reference. Access does not
establish redistribution/commercial reuse rights. PDF identity association and
table layout still require source review. No paywall or access challenge is
bypassed. Invalid HTML/challenge pages cannot become PDF evidence.

PDF parsing uses locked pdfplumber, retaining page text and detected tables.
Limits: 25 MB, 100 pages, 1,500 passages and 30 seconds in a disposable parser
process. Dense chart grids are skipped when a page has at least 1,000 drawing
edges; page text remains. There is no OCR or image transcription. Figure-only
measurements, supplementary files and damaged/complex PDFs need manual review.

## Structured local extraction

Select up to 16 passages / 24,000 source characters, then explicitly extract.
Only those passages reach the configured local Ollama model; no cloud fallback,
weight download or unselected-project evidence is available to the model.
Missing/offline/cloud models stop extraction. The schema is available at
`GET /literature/schema` and in `cvti.literature.AssayDraft`.

Each assay retains compound, target, tentative endpoint/activity/modality,
original value/units/uncertainty, species, PCSK9/LDLR constructs, variant,
method/conditions, controls, replicates and fitting details. Missing fields are
null. Internally the model selects field/passage/quotation IDs; application code
inserts exact source substrings. Endpoint classifications are LLM hypotheses.
Correct citation existence does not prove the chosen number belongs to that
compound, endpoint or unit. Automated scientific extraction accuracy has not
been established. Never silently accept normalized or invented measurements.

Source/evidence hashes, actual model name and digest, prompt/request/source-code
hashes, generation settings and raw responses accompany accepted drafts.
Truncation, invalid fields, unselected citations and model replacement reject a
draft. Failed attempts remain separate audit events, with rejected response
diagnostics where available. Extraction covers selected passages only; repeated
batches may describe the same assay and are not automatically deduplicated.

## Validation, review and assessment

Software flags missing metadata/controls, incompatible direct-PPI IC50 endpoints,
mixtures, modality/variant separation, nonpositive simple numerical values,
uncertainty at least as large as its simple numerical point estimate and optical
readout/interference concerns. Complex expressions are retained without forced
numeric parsing. Missing evidence means *not found in selected evidence*, not
proof that an experiment omitted a control. Concentration inconsistencies,
fit extrapolation and correct field assignments require expert source review.

Human review events record reviewer/date/source/rationale and `hold`, `exclude`
or `needs_information`. Events append; historical drafts remain unreviewed and
unchanged. There is no LLM review submission and no scientific approval endpoint.
The attribution record does not verify reviewer credentials. Existing dataset
curation is still required for any future qualified inclusion.

Select extraction records to save a deterministic Markdown/JSON assessment with
source citations, page/section/quotation locators, hashes, model identity, search
scope, review history and evidence gaps. It is a traceable draft, not an LLM's
unsupported global conclusion or a cross-study potency ranking.

## Interfaces and storage

All endpoints use `/literature`: `POST /search`, `/retrieve`, `/upload-pdf`,
`/extract`, `/reviews`, `/reports`; `GET /records?project_id=1&kind=document`,
`/records/{id}`, `/records/{id}/original`, `/schema`. Every ID is checked against
its project. IDs in another project return 404. This is local project scoping,
not multi-user authorization; keep the development API on loopback.

The additive Alembic revision `a62e8b75c319` creates `literature_records` with
immutable event payloads, parent links, raw source blobs and checksums. Both
SQLite and PostgreSQL use ordinary SQLAlchemy JSON/binary columns. No preexisting
measurement, review, dataset or experiment is rewritten. API startup/`cvti db
upgrade` applies normal migrations; follow the existing backup procedure first.

For a separate research run without upgrading/populating the main workspace:

```powershell
.venv/Scripts/python.exe scripts/literature_assessment.py `
  --query 'PCSK9 AND (diimidazole OR bibenzo OR brazilin OR quinolin OR Thaiprayoon)' `
  --start-date 2023-01-01 --end-date 2026-10-29 --limit 50 `
  --output data/literature/my-review --extract
```

The runner retains all search hits but retrieves a title-filtered primary-study
lead list relevant to the supplied assessment. Its selection policy and passage
IDs are logged; it is not a general systematic-review screening algorithm.
`--model` selects an already installed local model for that process only.
`--batch-size 1` reduces generation size; `--resume-extraction` continues an
existing isolated workspace without overwriting sources or successful batches.
Failures are retained. Results live in ignored `data/literature/.../literature.db`,
`source-inventory.json`, originals, `run-log.jsonl` and assessment Markdown/JSON.
These research outputs are not committed. To inspect this separate database in
the application, launch a separate local API with `DATABASE_URL` pointing to it;
see the normal local startup guide. Existing running servers need a restart to
load the new routes/page; development alone does not update a running process.

Service references: [PubMed E-utilities](https://www.nlm.nih.gov/dataguide/eutilities/utilities.html),
[Europe PMC API](https://dev.europepmc.org/RestfulWebService).
