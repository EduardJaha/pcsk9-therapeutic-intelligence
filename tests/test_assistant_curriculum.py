"""Controlled evidence tests; no model imports, inference, or database records."""
import importlib.util
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import assistant_curriculum as curriculum


def test_generated_targets_and_frozen_groups_are_consistent():
    groups = []
    questions = []
    for split in ('train', 'validation', 'test'):
        rows = [r for i in range(8) for r in curriculum.scenario(split, i)]
        assert {r['task'] for r in rows} == set(curriculum.TASKS)
        assert all(curriculum.assess(r['messages'][-1]['content'], r)['pass'] for r in rows)
        groups.append({r['source_group'] for r in rows})
        questions.append({json.loads(r['messages'][1]['content'])['question'] for r in rows})
        assert all(r['data_origin'] == 'synthetic_software_fixture' for r in rows)
    for a, b in ((0, 1), (0, 2), (1, 2)):
        assert not groups[a] & groups[b]
        assert not questions[a] & questions[b]


def test_missing_source_and_wrong_units_are_not_successes():
    compare = next(r for r in curriculum.scenario('test', 2) if r['task'] == 'endpoint_compare')
    value = json.loads(compare['messages'][-1]['content'])
    value['claims'].pop()
    assert not curriculum.assess(json.dumps(value), compare)['expected_sources_complete']
    extract = next(r for r in curriculum.scenario('test', 2) if r['task'] == 'extract')
    value = json.loads(extract['messages'][-1]['content'])
    value['claims'][0]['statement'] = value['claims'][0]['statement'].replace('IC50', 'EC50')
    assert not curriculum.assess(json.dumps(value), extract)['facts_preserved']


def test_added_numbers_and_unsupported_clinical_extensions_fail():
    row = curriculum.scenario('test', 3)[0]
    value = json.loads(row['messages'][-1]['content'])
    value['claims'][0]['statement'] += ' A 99999 percent success rate is established.'
    assert not curriculum.assess(json.dumps(value), row)['no_added_numbers']
    value = json.loads(row['messages'][-1]['content'])
    value['claims'][0]['statement'] += ' It is clinically effective.'
    assert not curriculum.assess(json.dumps(value), row)['no_role_or_clinical_overclaim']


def test_abstention_and_attribution_are_checked_separately():
    row = next(r for r in curriculum.scenario('test', 1) if r['task'] == 'missing')
    result = curriculum.assess('{"claims":[],"unanswered":[]}', row)
    assert result['schema_valid']
    assert not result['abstention_correct']
    assert not result['pass']


def test_origin_alias_correction_does_not_relax_values_or_citations():
    row = curriculum.scenario('validation', 4)[0]
    value = json.loads(row['messages'][-1]['content'])
    value['claims'][0]['statement'] = value['claims'][0]['statement'].replace('Synthetic', 'Fictional')
    raw = json.dumps(value)
    assert not curriculum.assess(raw, row)['facts_preserved']
    assert curriculum.assess(raw, row, origin_aliases=True)['pass']
    value['claims'][0]['statement'] += ' The reported success rate is 99999 percent.'
    assert not curriculum.assess(json.dumps(value), row, origin_aliases=True)['pass']
    value = json.loads(raw)
    value['claims'][0]['quote_id'] = 'Q998'
    assert not curriculum.assess(json.dumps(value), row, origin_aliases=True)['citations_valid']
