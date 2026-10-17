# Local pretrained research assistant

The first pretrained integration is an evidence assistant. It uses an existing
language model through local Ollama; it does not train an LLM or replace the
separate molecular prediction models. No external inference provider, API key or
paid service is required. The default installation leaves inference disabled.

## Setup

1. Install [Ollama](https://ollama.com/download) for your operating system.
2. From this repository, start a dedicated local runtime:

   ```bash
   python scripts/start_assistant.py
   ```

   This sets `OLLAMA_NO_CLOUD=1`, binds to loopback, and keeps model weights in
   ignored `data/ollama/models/`. Leave this terminal open. Stop any existing
   Ollama instance on port 11434 first if you want to use this separate store.

3. In another terminal, download an appropriate model. A small setup example is:

   ```bash
   ollama pull qwen3:1.7b
   ```

   This is a general language model, not a validated biomedical model. Its small
   size is useful for a functional laptop demonstration; evaluate its answers
   before relying on it. A different installed model can be configured without
   changing the code. Review its license, memory needs and provenance. Downloads
   need internet access; answering from supplied excerpts can run offline.

4. Add these settings to the repository's `.env` (copy `.env.example` first if
   needed):

   ```dotenv
   ASSISTANT_BASE_URL=http://127.0.0.1:11434
   ASSISTANT_MODEL=qwen3:1.7b
   ASSISTANT_TIMEOUT_SECONDS=45
   ```

5. Restart the research application with `cvti start`. The model server remains
   a separate process. Do not start a second application if its ports are occupied.

For a runtime extracted into `data/ollama/runtime/`, the launcher finds that
executable automatically. On macOS/Linux the pull command can also be
`data/ollama/runtime/ollama pull qwen3:1.7b`. Weights and the runtime are local
dependencies, not GitHub artifacts. After cloning, install/download them again.

The first version supports native local API/runtime processes. A runtime on the
host is not reachable through a container's loopback address; the supplied Docker
Compose stack does not yet connect the assistant to a separate host runtime.

## Use

Open **Research assistant**. Enter a question, then explicitly select a stored
dataset, a project experiment, or paste a source title and excerpt. An optional
source URL is attribution only: the application does not download that page or
claim to have read it. Pasted material is always labelled unreviewed. The workspace
can remain empty; pasted text is not imported as measurements or saved evidence.

Choose **Preview selected sources** to inspect context without contacting a model.
Choose **Ask local model** for an answer. The assistant:

- Searches only supplied documents and the explicitly selected dataset/report.
- Automatically includes the selected experiment's dataset. An independently
  selected dataset must match. Experiments must belong to the selected project.
  Datasets remain shared across this solo application; this is not tenant isolation.
- Ranks fixed overlapping excerpts with TF-IDF and sends at most five excerpts
  (8,000 characters) to the model. A longer source is not necessarily read in full.
- Requires structured claims and source/passage IDs, then inserts the original
  passage as an exact supporting quote. Unknown IDs, malformed/truncated output and model replacement cause
  the answer to be rejected. Rejection has no automatic ungrounded fallback.
- Returns model name/digest, generation settings, selected text, source hashes,
  offsets and dataset/experiment provenance in a downloadable JSON draft.

The model receives no tools. Requests do not change reviews, train models, execute
code, save predictions or write assistant history. Output is retained in the
browser session until changed/cleared; download a draft explicitly to retain it.
The model unloads after each answer to reduce idle memory usage.

## Interpretation and limitations

An exact quote can be real while the interpretation is wrong. These checks verify
attribution, not entailment, truth, completeness or scientific review. Synthetic
records and user-pasted claims remain such even if the model repeats them.
Selected reports describe existing calculations; generated prose does not create
new measured activities, molecular scores or calibrated confidence.

This release does not search publications automatically, read PDFs, perform
molecular docking, integrate a pretrained molecular checkpoint, fine-tune a model,
or establish research performance. PCSK9 real-data training remains dependent on
compatible reviewed assay data. The next molecular-model milestone is to select
a licensed checkpoint and benchmark its endpoint/modality coverage and potential
training-data overlap against the same frozen baseline protocol.

The loopback URL validator, disabled HTTP proxies/redirects, rejected cloud model
metadata and cloud-disabled launcher keep this integration local. Use a trusted
local Ollama service; these checks cannot establish how a modified server behaves.
There is no authentication or multi-user access control in this local release.

## API and verification

- `GET /assistant/status`: configured local model availability and digest.
- `POST /assistant/context`: preview evidence without inference.
- `POST /assistant/ask`: generate a cited draft from the same explicit inputs.

Both POST requests accept `question`, `project_id` (default 1), optional
`dataset_version_id` and `experiment_id`, and up to eight
`documents: [{"title": "...", "text": "...", "url": "https://..."}]`.

Blank questions or conflicting selection return 422. Unavailable models return
503. Failed generation/citation checks return 502. Empty evidence returns an
`insufficient_evidence` response without contacting the model. Client-side form
errors clear the previous draft so it cannot be mistaken for the current answer.

Offline checks: `python -m pytest -q tests/test_assistant.py tests/test_dashboard.py`.
They use temporary databases and mocked inference; they never download weights
or contact a real model. Live inference checks must be recorded separately from
these tests and do not constitute a biomedical benchmark.

Implementation references: [Ollama chat API](https://docs.ollama.com/api/chat),
[local model inventory](https://docs.ollama.com/api/tags), and
[Qwen3 model library](https://ollama.com/library/qwen3).
