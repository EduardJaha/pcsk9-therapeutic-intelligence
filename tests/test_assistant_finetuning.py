"""Offline safeguards for the optional training script; never imports Unsloth."""
import importlib.util
import json
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    "finetune_assistant", Path(__file__).resolve().parents[1] / "scripts/finetune_assistant.py")
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


def test_frozen_dataset_is_reproducible_and_document_disjoint(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    pilot.prepare(first)
    pilot.prepare(second)
    manifest = json.loads((first / "dataset-manifest.json").read_text(encoding="utf-8"))
    for source, info in manifest["sources"].items():
        assert pilot.digest(first / "sources" / source) == info["sha256"]
    documents, excerpts = [], []
    for split in ("train", "validation", "test"):
        assert (first / f"{split}.jsonl").read_bytes() == (second / f"{split}.jsonl").read_bytes()
        rows = pilot.load_rows(first, split)
        assert {r["task"] for r in rows} == {"extract", "missing"}
        assert any(r["adversarial"] for r in rows)
        documents.append({r["source_document"] for r in rows})
        excerpts.append({r["source_excerpt_sha256"] for r in rows})
        for row in rows:
            answer = row["messages"][-1]["content"]
            assert pilot.assess_answer(answer, row)["task_behavior_pass"]
    for a, b in ((0, 1), (0, 2), (1, 2)):
        assert not documents[a] & documents[b]
        assert not excerpts[a] & excerpts[b]
    with pytest.raises(ValueError, match="already frozen"):
        pilot.prepare(first)


def test_changed_frozen_dataset_is_rejected(tmp_path):
    pilot.prepare(tmp_path)
    with (tmp_path / "train.jsonl").open("a", encoding="utf-8") as stream:
        stream.write("{}\n")
    with pytest.raises(ValueError, match="checksum mismatch"):
        pilot.load_rows(tmp_path, "train")


@pytest.fixture
def example(tmp_path):
    pilot.prepare(tmp_path)
    return next(r for r in pilot.load_rows(tmp_path, "test") if r["task"] == "extract")


def test_invalid_output_and_fabricated_citations_fail(example):
    assert not pilot.assess_answer("APPROVED", example)["json_schema_valid"]
    answer = json.loads(example["messages"][-1]["content"])
    answer["claims"][0]["quote_id"] = "Q876"
    assessed = pilot.assess_answer(json.dumps(answer), example)
    assert assessed["json_schema_valid"]
    assert not assessed["citation_ids_valid"]
    assert not assessed["task_behavior_pass"]


def test_citation_existence_does_not_count_as_claim_support(example):
    answer = json.loads(example["messages"][-1]["content"])
    answer["claims"][0]["statement"] = "This compound is clinically safe and effective."
    assessed = pilot.assess_answer(json.dumps(answer), example)
    assert assessed["citation_ids_valid"]
    assert not assessed["extractive_claims_only"]


def test_missing_evidence_requires_abstention(tmp_path):
    pilot.prepare(tmp_path)
    example = next(r for r in pilot.load_rows(tmp_path, "test") if r["task"] == "missing")
    assert not pilot.assess_answer('{"claims":[],"unanswered":[]}', example)["task_behavior_pass"]
    answer = example["messages"][-1]["content"]
    assert pilot.assess_answer(answer, example)["task_behavior_pass"]


@pytest.fixture
def parent_run(tmp_path):
    parent = tmp_path / 'parent'
    pilot.prepare(parent)
    (parent / 'adapter').mkdir()
    (parent / 'adapter' / 'adapter_model.safetensors').write_bytes(b'fake weights for offline integrity checks')
    (parent / 'checkpoints').mkdir()
    pilot.write_json(parent / 'checkpoints' / 'trainer_state.json', {'global_step': 25})
    pilot.write_json(parent / 'run.json', {
        'status': 'complete', 'training_metrics': {'epoch': 1.0},
        'adapter_files': {'adapter_model.safetensors': pilot.digest(parent / 'adapter' / 'adapter_model.safetensors')},
        'dataset_manifest_sha256': pilot.digest(parent / 'dataset-manifest.json'),
    })
    return parent


def test_continuation_preserves_parent_and_evaluation_partitions(tmp_path, parent_run):
    original = pilot.digest(parent_run / 'run.json')
    target = tmp_path / 'continued'
    pilot.prepare_continuation(target, parent_run)
    lineage = json.loads((target / 'continuation.json').read_text())
    assert lineage['parent_run_sha256'] == original
    assert lineage['previous_optimizer_steps'] == 25
    assert lineage['previous_epochs'] == 1.0
    assert 'fresh optimizer' in lineage['mode']
    assert 'validation only' in lineage['evaluation_partition']
    for split in ('train', 'validation', 'test'):
        assert (target / f'{split}.jsonl').read_bytes() == (parent_run / f'{split}.jsonl').read_bytes()
    assert pilot.digest(parent_run / 'run.json') == original
    with pytest.raises(ValueError, match='already exists'):
        pilot.prepare_continuation(target, parent_run)


def test_continuation_rejects_changed_weights_before_creating_run(tmp_path, parent_run):
    (parent_run / 'adapter' / 'adapter_model.safetensors').write_bytes(b'changed')
    target = tmp_path / 'continued'
    with pytest.raises(ValueError, match='Parent adapter changed'):
        pilot.prepare_continuation(target, parent_run)
    assert not target.exists()


def test_more_training_does_not_automatically_pass_development_gate():
    baseline = dict.fromkeys(('json_schema_valid', 'citation_ids_valid', 'extractive_claims_only', 'task_behavior_pass'), 1.0)
    assert pilot.continuation_acceptable(0.004, 0.003, baseline, baseline)
    assert not pilot.continuation_acceptable(0.004, 0.005, baseline, baseline)
    worse = {**baseline, 'task_behavior_pass': 0.875}
    assert not pilot.continuation_acceptable(0.004, 0.003, baseline, worse)


def test_production_json_order_preserves_answer_semantics_and_citation_order():
    original = '{"claims":[{"statement":"Synthetic value 12 nM.","source_id":"S2","quote_id":"Q7"}],"unanswered":[]}'
    ordered = pilot.serialized_answer(original, canonical=True)
    assert json.loads(ordered) == json.loads(original)
    assert ordered.index('quote_id') < ordered.index('source_id') < ordered.index('statement')
    assert pilot.serialized_answer(original, canonical=False) == original
