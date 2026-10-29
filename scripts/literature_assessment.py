"""Run a bounded evidence harvest into a NEW, isolated local research workspace.

Network retrieval is public. Optional extraction uses the configured local model.
No approval, training, automatic source inclusion or main-workspace change occurs.
"""
import argparse
import json
import re
from pathlib import Path

from cvti import literature as lab, literature_sources as sources
from cvti.db import init_db, make_engine, session_factory
from cvti.models import LiteratureRecord
from sqlalchemy import select


def candidates(passages):
    """Visible selection policy, not a completeness claim or scientific classifier."""
    result = []
    for p in passages:
        location = p['locator'].lower()
        value = p['text'].lower()
        if ((p['kind'] in {'abstract', 'table'} and re.search(r'pcsk9|ldlr|ic.?50|inhibit|neutraliz', value)) or
            (p['kind'] == 'page_text' and re.search(r'ic.{0,3}50|ic.{0,3}.?values|neutralization', value)) or
            (re.search(r'binding|neutraliz|statistic', location) and not re.search(r'synthesis|docking', location))):
            result.append(p['id'])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--query', action='append', required=True)
    parser.add_argument('--start-date', required=True)
    parser.add_argument('--end-date', required=True)
    parser.add_argument('--limit', type=int, default=20)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--extract', action='store_true', help='Send selected public passages to the configured local model')
    parser.add_argument('--model', help='An already installed local model; does not change application settings')
    parser.add_argument('--batch-size', type=int, choices=[1,2,3,4], default=2)
    parser.add_argument('--resume-extraction', action='store_true', help='Continue extraction from this isolated workspace without retrieving again')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    database = args.output / 'literature.db'
    if database.exists() and not args.resume_extraction:
        parser.error('Output database already exists; choose a new directory or use --resume-extraction')
    engine = make_engine('sqlite:///' + database.resolve().as_posix())
    init_db(engine)
    factory = session_factory(engine)
    if args.model:
        from cvti import assistant
        settings = assistant.get_settings().model_copy(update={'assistant_model': args.model})
        assistant.get_settings = lambda: settings
    journal_path = args.output / 'run-log.jsonl'

    def log(event):
        with journal_path.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps({'at': sources.now(), **event}, ensure_ascii=False) + '\n')
        visible = {key: ({k: v for k, v in value.items() if k != 'diagnostic'}
                          if isinstance(value, dict) else value) for key, value in event.items()}
        print(json.dumps(visible, ensure_ascii=True), flush=True)

    try:
        with factory() as session:
            if not args.resume_extraction:
                seen = set()
                for query in args.query:
                    found = sources.search(query, args.limit, start_date=args.start_date, end_date=args.end_date)
                    logs = json.dumps(found.pop('response_log'), ensure_ascii=False).encode()
                    search = lab.save(session, 1, 'search', found, content=logs)
                    log({'search_id': search.id, 'query': query, 'providers': found['providers']})
                    for publication in found['publications']:
                        # Retain all search hits; retrieve only identified studies matching the scope.
                        title = publication['title']
                        if not (re.search(r'PCSK9|proprotein convertase', title, re.I) and re.search(
                            r'diimidazole|bibenzo|brazilin|methanone|nanobodies from synthetic|structural modification approach|truncated cyclic|peptide inhibitor|TPP-4', title, re.I)):
                            continue
                        key = publication.get('pmid') or publication.get('doi') or title
                        if key in seen:
                            continue
                        seen.add(key)
                        parent = lab.save(session, 1, 'publication', publication, parent_id=search.id)
                        documents = []
                        if publication.get('pmcid'):
                            for kind in ('xml', 'pdf'):
                                try:
                                    raw, parsed = sources.download(publication['pmcid'], kind)
                                    parsed['title'] = title
                                    record = lab.save(session, 1, 'document', parsed, parent_id=parent.id, content=raw)
                                    (args.output / f"source-{record.id}.{kind}").write_bytes(raw)
                                    documents.append(record.id)
                                    log({'document_id': record.id, 'format': kind, 'title': title,
                                         'passages': len(parsed['passages']), 'sha256': record.content_sha256})
                                except Exception as exc:
                                    failure = {'format': kind, 'message': str(exc)[:500], 'at': sources.now()}
                                    lab.save(session, 1, 'retrieval_failure', failure, parent_id=parent.id)
                                    log({'title': title, 'failure': failure})
                        if not documents and publication.get('abstract'):
                            value = publication['abstract']
                            parsed = {'title': title, 'format': 'abstract', 'url': publication['url'],
                                'parser': 'provider-abstract-v1', 'passages': [{'id': 'P1', 'kind': 'abstract',
                                'locator': 'Provider abstract; not full text', 'text': value}],
                                'limitations': ['Abstract only; primary tables, methods and supplements unavailable.']}
                            record = lab.save(session, 1, 'document', parsed, parent_id=parent.id, content=value.encode())
                            log({'document_id': record.id, 'format': 'abstract', 'title': title})
            if args.extract:
                documents = session.scalars(select(LiteratureRecord).where(LiteratureRecord.kind == 'document')).all()
                # XML and PDF can contain complementary table/figure labels.
                for document in documents:
                    if not re.search(r'PCSK9|proprotein convertase', document.payload_json['title'], re.I):
                        continue
                    if re.search(r'pyrroloquinoline', document.payload_json['title'], re.I):
                        continue
                    selected = candidates(document.payload_json['passages'])
                    log({'document_id': document.id, 'selected_passage_ids': selected,
                         'selection_policy': 'assay-tables-abstract-binding-methods-v1; figure pixels and supplements excluded'})
                    for start in range(0, len(selected), args.batch_size):
                        identifiers = selected[start:start+args.batch_size]
                        existing = session.scalars(select(LiteratureRecord).where(
                            LiteratureRecord.parent_id == document.id, LiteratureRecord.kind == 'extraction')).all()
                        valid_existing = False
                        for previous in existing:
                            if previous.payload_json['selected_passage_ids'] != identifiers:
                                continue
                            lab.verify(previous)
                            try:
                                generated = lab.GeneratedExtraction(assays=[lab.AssayDraft.model_validate(
                                    {key: value for key, value in row.items() if key in lab.AssayDraft.model_fields})
                                    for row in previous.payload_json['assays']], gaps=previous.payload_json['gaps'])
                                lab.check_facts(generated, [p for p in document.payload_json['passages'] if p['id'] in identifiers])
                                valid_existing = True
                            except ValueError:
                                continue
                        if valid_existing:
                            continue
                        try:
                            result = lab.extract(document, identifiers)
                            record = lab.save(session, 1, 'extraction', result, parent_id=document.id)
                            log({'extraction_id': record.id, 'document_id': document.id, 'assays': len(result['assays'])})
                        except Exception as exc:
                            failure = {'passage_ids': identifiers, 'message': str(exc)[:500], 'at': sources.now()}
                            if hasattr(exc, 'diagnostic'):
                                failure['diagnostic'] = exc.diagnostic
                            lab.save(session, 1, 'extraction_failure', failure, parent_id=document.id)
                            log({'document_id': document.id, 'extraction_failure': failure})
            extraction_ids = list(session.scalars(select(LiteratureRecord.id).where(LiteratureRecord.kind == 'extraction')))
            if extraction_ids:
                result = lab.assessment(session, 1, extraction_ids)
                lab.save(session, 1, 'report', result)
                (args.output / 'assessment.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
                (args.output / 'assessment.md').write_text(lab.render_report(result), encoding='utf-8')
            inventory = [lab.summary(r, True) for r in session.scalars(select(LiteratureRecord).where(
                LiteratureRecord.kind.in_(['search', 'publication', 'document', 'retrieval_failure', 'extraction_failure'])))]
            (args.output / 'source-inventory.json').write_text(json.dumps(inventory, indent=2, ensure_ascii=False), encoding='utf-8')
            log({'complete': True, 'extractions': len(extraction_ids), 'database': str(database.resolve())})
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
