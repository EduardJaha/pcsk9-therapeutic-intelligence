"""Explicit literature retrieval, local drafts, append-only reviews and exports."""
import base64
import binascii
import json
from datetime import date
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import Field
from sqlalchemy import select

from cvti import literature as lab, literature_sources as sources
from cvti.assistant import AssistantUnavailable, InvalidModelAnswer
from cvti.literature import Strict
from cvti.models import LiteratureRecord
from cvti.registry import project_exists


class Search(Strict):
    project_id: int = Field(default=1, gt=0)
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=20, ge=1, le=50)
    start_date: date | None = None
    end_date: date | None = None


class Retrieve(Strict):
    project_id: int = Field(default=1, gt=0)
    search_id: int = Field(gt=0)
    publication_index: int = Field(ge=0)
    format: Literal['xml', 'pdf', 'abstract'] = 'xml'


class Upload(Strict):
    project_id: int = Field(default=1, gt=0)
    publication_id: int = Field(gt=0)
    pdf_base64: str = Field(min_length=1, max_length=34_000_000)
    source_reference: str = Field(min_length=1, max_length=2000)


class Extraction(Strict):
    project_id: int = Field(default=1, gt=0)
    document_id: int = Field(gt=0)
    passage_ids: list[str] = Field(min_length=1, max_length=16)


class Review(Strict):
    project_id: int = Field(default=1, gt=0)
    extraction_id: int = Field(gt=0)
    reviewer: str = Field(min_length=2, max_length=120)
    reviewed_on: date
    disposition: Literal['hold', 'exclude', 'needs_information']
    rationale: str = Field(min_length=10, max_length=5000)
    source_reference: str = Field(min_length=5, max_length=2000)


class Report(Strict):
    project_id: int = Field(default=1, gt=0)
    extraction_ids: list[int] = Field(min_length=1, max_length=100)


def router(factory):
    api = APIRouter(prefix='/literature', tags=['Literature evidence'])

    def error(exc):
        status = (404 if isinstance(exc, LookupError) else 503 if isinstance(exc, AssistantUnavailable)
                  else 422)
        return HTTPException(status, str(exc))

    @api.get('/schema')
    def schema():
        return {'schema_version': 'literature-assay-v1', 'schema': lab.GeneratedExtraction.model_json_schema(),
                'notice': lab.NOTICE}

    @api.get('/records')
    def records(project_id: int = Query(1, gt=0), kind: Literal['search','publication','document','extraction','review','report','retrieval_failure','extraction_failure'] | None = None):
        try:
            with factory() as session:
                project_exists(session, project_id)
                query = select(LiteratureRecord).where(LiteratureRecord.project_id == project_id)
                if kind:
                    query = query.where(LiteratureRecord.kind == kind)
                return [lab.summary(r) for r in session.scalars(query.order_by(LiteratureRecord.id.desc()).limit(500))]
        except (LookupError, ValueError) as exc:
            raise error(exc) from exc

    @api.get('/records/{identifier}')
    def record(identifier: int, project_id: int = Query(1, gt=0)):
        try:
            with factory() as session:
                return lab.summary(lab.get(session, project_id, identifier), True)
        except (LookupError, ValueError) as exc:
            raise error(exc) from exc

    @api.get('/records/{identifier}/original')
    def original(identifier: int, project_id: int = Query(1, gt=0)):
        try:
            with factory() as session:
                record = lab.get(session, project_id, identifier)
                if record.content_blob is None:
                    raise LookupError('This record has no retained original file')
                media = {'pdf': 'application/pdf', 'xml': 'application/xml'}.get(record.payload_json.get('format'), 'application/octet-stream')
                return Response(record.content_blob, media_type=media,
                                headers={'Content-Disposition': f'attachment; filename="literature-{identifier}.bin"'})
        except (LookupError, ValueError) as exc:
            raise error(exc) from exc

    @api.post('/search')
    def search(request: Search):
        try:
            with factory() as session:
                project_exists(session, request.project_id)
                result = sources.search(request.query, request.limit,
                    start_date=request.start_date.isoformat() if request.start_date else None,
                    end_date=request.end_date.isoformat() if request.end_date else None)
                logs = json.dumps(result.pop('response_log'), ensure_ascii=False).encode()
                return lab.summary(lab.save(session, request.project_id, 'search', result, content=logs), True)
        except (ValueError, LookupError) as exc:
            raise error(exc) from exc

    @api.post('/retrieve')
    def retrieve(request: Retrieve):
        try:
            with factory() as session:
                search = lab.get(session, request.project_id, request.search_id, 'search')
                rows = search.payload_json['publications']
                if request.publication_index >= len(rows):
                    raise ValueError('Publication is not in the selected search')
                publication = rows[request.publication_index]
                parent = lab.save(session, request.project_id, 'publication', publication, parent_id=search.id)
                try:
                    if request.format == 'abstract':
                        value = publication.get('abstract', '').strip()
                        if not value:
                            raise ValueError('No abstract supplied by the provider')
                        raw = value.encode()
                        parsed = {'format': 'abstract', 'url': publication['url'], 'parser': 'provider-abstract-v1',
                            'passages': [{'id': 'P1', 'locator': 'Provider abstract; not full text', 'kind': 'abstract', 'text': value}],
                            'limitations': ['Abstract only; full methods, tables and figures unavailable.'],
                            'license': 'Check original source reuse terms', 'retrieved_at': sources.now()}
                    else:
                        raw, parsed = sources.download(publication.get('pmcid') or '', request.format)
                except (ValueError, httpx.HTTPError) as exc:
                    # Retain failure as a separate event, never a successful document.
                    lab.save(session, request.project_id, 'retrieval_failure', {
                        'format': request.format, 'message': 'Full text unavailable or invalid; upload a legally accessible PDF or select abstract.',
                        'attempted_at': sources.now()}, parent_id=parent.id)
                    raise ValueError('Full text unavailable or invalid; upload an accessible PDF using publication '
                                     f'{parent.id}, or explicitly retrieve its abstract') from exc
                parsed['title'] = publication['title']
                return lab.summary(lab.save(session, request.project_id, 'document', parsed, parent_id=parent.id, content=raw), True)
        except (ValueError, LookupError) as exc:
            raise error(exc) from exc

    @api.post('/upload-pdf')
    def upload(request: Upload):
        try:
            with factory() as session:
                publication = lab.get(session, request.project_id, request.publication_id, 'publication')
                raw = base64.b64decode(request.pdf_base64, validate=True)
                parsed = sources.parse_pdf(raw)
                parsed.update(format='pdf', title=publication.payload_json['title'], source_reference=request.source_reference,
                              retrieved_at=sources.now(), origin='user_supplied_pdf; publication association requires verification')
                return lab.summary(lab.save(session, request.project_id, 'document', parsed,
                                            parent_id=publication.id, content=raw), True)
        except (ValueError, LookupError, binascii.Error) as exc:
            raise error(exc) from exc

    @api.post('/extract')
    def extract(request: Extraction):
        try:
            with factory() as session:
                document = lab.get(session, request.project_id, request.document_id, 'document')
                try:
                    result = lab.extract(document, request.passage_ids)
                except lab.InvalidExtraction as exc:
                    lab.save(session, request.project_id, 'extraction_failure',
                        {'message': str(exc), 'diagnostic': exc.diagnostic, 'created_at': sources.now()}, parent_id=document.id)
                    raise
                except AssistantUnavailable as exc:
                    lab.save(session, request.project_id, 'extraction_failure',
                        {'message': str(exc), 'selected_passage_ids': request.passage_ids, 'created_at': sources.now()}, parent_id=document.id)
                    raise
                return lab.summary(lab.save(session, request.project_id, 'extraction', result, parent_id=document.id), True)
        except (ValueError, LookupError, AssistantUnavailable, InvalidModelAnswer) as exc:
            raise error(exc) from exc

    @api.post('/reviews')
    def review(request: Review):
        try:
            if request.reviewed_on > date.today():
                raise ValueError('Review date cannot be in the future')
            with factory() as session:
                lab.get(session, request.project_id, request.extraction_id, 'extraction')
                payload = request.model_dump(mode='json', exclude={'project_id', 'extraction_id'})
                payload['notice'] = 'Recorded human disposition; does not approve scientific validity or admit data to training.'
                return lab.summary(lab.save(session, request.project_id, 'review', payload, parent_id=request.extraction_id), True)
        except (ValueError, LookupError) as exc:
            raise error(exc) from exc

    @api.post('/reports')
    def report(request: Report):
        try:
            with factory() as session:
                result = lab.assessment(session, request.project_id, request.extraction_ids)
                record = lab.save(session, request.project_id, 'report', result)
                return {'id': record.id, 'report': result, 'markdown': lab.render_report(result)}
        except (ValueError, LookupError) as exc:
            raise error(exc) from exc

    return api
