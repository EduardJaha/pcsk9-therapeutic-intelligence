# Local assistant fine-tuning pilot

The optional `scripts/finetune_assistant.py` uses a separate, installed Unsloth
environment. It does not change the application's locked dependencies, open the
research database, curate assays, or train molecular predictors.

This is a documentation-derived software-behavior experiment. Its generated
examples teach passage attribution, the assistant's JSON format, missing-evidence
responses and handling of malicious instructions inside evidence. They are not
expert-reviewed biomedical answers, real assay measurements, or scientific
validation. This pilot does not demonstrate better scientific reasoning.

The [28 October broader evaluation](assistant-evaluation.md) adds endpoint,
conflict, report and adversarial tasks with production-constrained generation.
It preserves the pilot below as history and records selection separately from
training loss. All generated examples remain outside the research database.

## Completed pilot on this PC — 27 October 2026

The current active model is the subsequent continuation
`pcsk9-assistant:continued-20261027-02`. Its files and detailed report are under
`data/assistant-training/2026-10-27-continued-02/`. It adds one pass through the
same 200 examples at learning rate 0.00001, for two passes and 50 optimizer
steps cumulatively. Learned adapter weights were continued with a fresh
optimizer/schedule. No new biomedical training examples were added.

On the unchanged 16-example validation partition, loss decreased from
0.0045478423 to 0.0008687152. All eight selected validation exercises passed the
mechanical checks. Both old and new GGUF models passed the same six application
regression cases in a disposable database. The historical test set was not
used for this selection. A live request after activation confirmed the new
model/digest, approximately 2.9 GB of GPU allocation and an unchanged research
summary. Eight offline script tests passed. These are development checks on
small generated examples, not independent scientific validation.

The local `.env` now selects the continuation. Both Ollama tags remain in the
original pilot's isolated model store, so the original model can be selected
again without retraining. The original pilot's reports and adapter are preserved.
The following bullets describe that original run.

- Qwen3 1.7B cached revision `a972f4304f86a0a705d35b378d7a7675d58063a7`,
  trained with installed Unsloth 2026.10.9 on an RTX 3060 with 12 GB VRAM.
- 200 training, 16 validation and 24 held-out examples; one epoch/25 optimizer
  steps. Training took about 128 seconds after model loading and compilation.
- All 12 selected held-out template exercises passed the mechanical checks.
  The baseline passed none of these raw format checks: the prompt refers to a
  schema but the raw generator is not supplied that schema or a constrained
  decoder. This result must not be read as an improvement over the application's
  existing schema-constrained assistant or as scientific performance.
- Q8_0 GGUF export registered as `pcsk9-assistant:pilot-20261027` in a separate
  local Ollama store under the run directory. GGUF SHA-256:
  `8fd383a7d3582b8ea9d80fc53f29916fc3fbcf0d3862fd32eb7494073890c198`.
- Six live application checks passed in a disposable database: empty context,
  extraction, two missing-evidence questions, embedded malicious instructions
  and selecting a relevant passage from multiple sources. The database summary
  stayed unchanged. These synthetic checks do not establish general robustness.
- 37 relevant offline tests passed; five script tests were rerun after export
  changes. The existing Starlette/httpx deprecation warning remains.

Artifacts, original source copies, logs and reports are under ignored
`data/assistant-training/2026-10-27-pilot/`. The saved `training-script.py` is the
exact source used for training; the maintained script includes the subsequent
export compatibility fix. `run.json` describes the completed training/evaluation;
separate export/deployment manifests identify the merged and quantized artifacts.
The first native merge/export attempts failed; logs are preserved and the
successful compatible export is recorded separately. No retraining was needed.

To serve the registered pilot, run its `Start-pilot.ps1` in PowerShell and leave
the terminal open. It binds to `127.0.0.1:11435`, disables cloud inference and
uses the run's `ollama-models/` store. Ctrl+C stops that server. Set the following
in the application's `.env`, then restart the application:

```dotenv
ASSISTANT_BASE_URL=http://127.0.0.1:11435
ASSISTANT_MODEL=pcsk9-assistant:pilot-20261027
```

The initial training step left application configuration unchanged. A subsequent
connection step on 27 October configured the local `.env` with
`ASSISTANT_AUTOSTART=true`, the pilot's model/store and port 11435. The normal
`cvti start` command now starts its runtime automatically, so the separate
`Start-pilot.ps1` is optional. See [normal startup](pretrained-assistant.md).
The existing Ollama instance on port 11434 is preserved.

## Reproduce a new run

Use an existing local `unsloth/Qwen3-1.7B-unsloth-bnb-4bit` checkpoint and the Python
interpreter belonging to Unsloth. On this Windows PC that interpreter is
`C:\Users\STORM\.unsloth\studio\unsloth_studio\Scripts\python.exe`.
Keep all outputs under ignored `data/`; use a new run directory for each experiment.

```powershell
$trainer = 'C:\Users\STORM\.unsloth\studio\unsloth_studio\Scripts\python.exe'
$run = 'data/assistant-training/my-new-run'
$checkpoint = 'C:\path\to\existing\Qwen3-1.7B\snapshot'
& $trainer scripts/finetune_assistant.py prepare --run-dir $run
& $trainer scripts/finetune_assistant.py train --run-dir $run --model $checkpoint --merge
```

## Continue a saved adapter

Continue into a new run directory to preserve the deployed model and historical
reports. The script verifies the completed parent's run manifest, learned adapter
hashes and frozen dataset, then copies the original document snapshots and exact
train/validation/test assignments. It does not generate replacement examples or
load research database records.

```powershell
$parent = 'data/assistant-training/2026-10-27-pilot'
$run = 'data/assistant-training/my-continuation'
& $trainer scripts/finetune_assistant.py prepare-continuation --run-dir $run --parent-run $parent
& $trainer scripts/finetune_assistant.py train --run-dir $run --model $checkpoint --learning-rate 0.00001
```

This loads the parent's learned LoRA weights and trains one more epoch with a
fresh optimizer and learning-rate schedule. It is not an exact restart of the
parent's optimizer/RNG state. The new default learning rate is 0.00001; dataset,
base checkpoint and adapter architecture are preserved. Repeated examples add
training exposure, not new scientific evidence or unique training records.

The parent and continued adapters are compared on the same frozen validation
exercises and full validation loss. The historical test set is preserved and is
not used to select the continuation. Earlier test results have already been
observed and cannot serve as an untouched independent evaluation.

`run.json` records parent hashes, optimizer reset, additional/cumulative epochs
and optimizer updates, validation results and a development gate. That gate
requires non-increasing validation loss and no mechanical behavior regressions;
it does not establish biomedical accuracy. Export and application checks are
still required before activating a candidate. The active assistant is not
changed automatically by training.

Watch `training.log` and `checkpoints/trainer_state.json` for this run's progress.
Cumulative totals are in `run.json`. A completed training schedule is not a
percentage of scientific knowledge learned.

`prepare` reads only the named repository documents and extracts the application's
system prompt without importing its services. It freezes conversational JSONL
files and SHA-256 checksums. Entire documents are assigned to train, validation
or test; exact duplicate excerpts are removed across splits. Related documents
may still repeat the same facts, and questions are generated from a small set of
templates. These held-out exercises are not an independent scientific benchmark.
Training refuses changed JSONL files and examples exceeding its context limit.

The pilot uses 4-bit QLoRA, rank 16/alpha 32, one epoch, batch size 1, accumulation
8, learning rate 0.0001, seed 42 and a 2,048-token context. Only assistant answer
tokens contribute to training loss. Validation loss is recorded at the end; no
test-based model selection or hyperparameter tuning is performed.

The runner uses offline Hugging Face loading, disables external reporting and
telemetry, and directs compilation and temporary files into the run directory.
Native CUDA compilation requires execution access; Windows sandbox restrictions
may prevent the compiler from launching. No cloud fallback is attempted.

## Inspect the result

The run directory contains dataset and run manifests, adapter weights/tokenizer,
trainer state, logs, exact evaluation assignments and original generated outputs.
The run records the cached base revision, weight/config hashes, package versions,
GPU identity, parameters and output hashes. `--merge` also saves a separate
16-bit merged model for conversion to GGUF. The exporter dequantizes a copy of
the actual NF4 training base, then merges the adapter; it does not recover the
original unquantized model. The installed runtime's PEFT compatibility fix is
used without changing installed packages. Large weights stay untracked.

If training completed but export failed, the adapter can be exported separately
without repeating training:

```powershell
& $trainer scripts/finetune_assistant.py export --run-dir $run --model $checkpoint
```

Baseline and trained models answer the same frozen 12-example subset: six
extraction and six missing-evidence exercises. Generation is greedy and
unconstrained. Reported checks cover JSON structure, resolving citation IDs,
literal extractive claims and expected task behavior. Resolving an ID is not
proof that the associated claim is supported; a separate exact-text check is
reported. Paraphrases can fail that conservative check despite being reasonable.

The raw generation check does not supply Ollama's schema-constrained decoder;
its format scores must not be presented as a comparison against the production
assistant's existing constrained generation. All outputs need human inspection.
An answer can pass every mechanical check and still be scientifically wrong.

## Use with the application

Convert the merged model to GGUF using a compatible local llama.cpp converter,
then register it in local Ollama under a new name. Preserve the Qwen3 chat
template and disabled-thinking behavior. Test the exported model separately:
conversion or quantization can change answers. Keep the original model installed.

To select a registered model, set these values in the application's `.env` and
restart the API:

```dotenv
ASSISTANT_BASE_URL=http://127.0.0.1:11435
ASSISTANT_MODEL=pcsk9-assistant:pilot-20261027
```

Keep the existing evidence-selection, model identity, source hashes and citation
checks. See [the assistant guide](pretrained-assistant.md). Training does not
authorize the assistant to execute tools, submit reviews, approve assays or
create molecular scores. Meaningful biomedical adaptation requires sourced,
appropriately reviewed examples and a substantially stronger evaluation set.
