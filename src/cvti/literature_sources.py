"""Bounded public literature retrieval and page/section-preserving extraction."""
import base64
import hashlib
import io
import json
import re
import subprocess
import sys
import threading
import time
from urllib.parse import parse_qs, urljoin, urlsplit
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from importlib.metadata import version

import httpx

EUTILS = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils'
EPMC = 'https://www.ebi.ac.uk/europepmc/webservices/rest'
MAX_BYTES = 25_000_000
_lock = threading.Lock()
_last_request = 0.0


def sha(value):
    return hashlib.sha256(value).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def public_client():
    return httpx.Client(timeout=25, follow_redirects=False, trust_env=False,
                        headers={'User-Agent': 'PCSK9Lab/0.2 literature research'})


def fetch(client, url, *, params=None, log=None, _redirects=0):
    global _last_request
    for attempt in range(3):
        # Shared limiter also covers parallel API callers. No API key required.
        with _lock:
            time.sleep(max(0, .36 - (time.monotonic() - _last_request)))
            _last_request = time.monotonic()
        try:
            with client.stream('GET', url, params=params) as response:
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_BYTES:
                        raise ValueError('Public source exceeds the 25 MB download limit')
                raw = bytes(body)
                if log is not None:
                    log.append({'url': str(response.url), 'retrieved_at': now(),
                                'status': response.status_code, 'sha256': sha(raw),
                                'body_base64': base64.b64encode(raw).decode('ascii')})
                if response.status_code in {301, 302, 303, 307, 308}:
                    target = urljoin(str(response.url), response.headers.get('Location', ''))
                    old, new = urlsplit(str(response.url)), urlsplit(target)
                    if (_redirects >= 3 or new.scheme != 'https' or new.netloc != old.netloc
                            or new.username or new.password):
                        raise ValueError('Repository redirect left the trusted origin or exceeded the redirect limit')
                    return fetch(client, target, log=log, _redirects=_redirects+1)
                if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                    retry = response.headers.get('Retry-After', '')
                    time.sleep(min(float(retry), 5) if retry.isdigit() else 1 + attempt)
                    continue
                response.raise_for_status()
                return raw
        except httpx.TransportError:
            if attempt == 2:
                raise ValueError('Public literature service is unavailable; retry later') from None
    raise ValueError('Public literature request failed')


def xml(raw):
    if b'<!ENTITY' in raw.upper():
        raise ValueError('XML entity declarations are not supported')
    return ET.fromstring(raw)


def text(node):
    return ''.join(node.itertext()).strip() if node is not None else ''


def search(query, limit=20, client=None, start_date=None, end_date=None):
    if not query.strip() or len(query) > 2000 or not 1 <= limit <= 50:
        raise ValueError('Enter a query and a limit between 1 and 50 per provider')
    from datetime import date
    if start_date and end_date and date.fromisoformat(start_date) > date.fromisoformat(end_date):
        raise ValueError('Search start date must precede end date')
    bounds = {key: date.fromisoformat(value).isoformat() for key, value in
              [('start', start_date), ('end', end_date)] if value}
    owned = client is None
    client = client or public_client()
    results, providers, logs = [], {}, []
    try:
        for provider in ('pubmed', 'europe_pmc'):
            try:
                if provider == 'pubmed':
                    dated = {'datetype': 'pdat'} if bounds else {}
                    if start_date: dated['mindate'] = start_date.replace('-', '/')
                    if end_date: dated['maxdate'] = end_date.replace('-', '/')
                    found = json.loads(fetch(client, f'{EUTILS}/esearch.fcgi', params={
                        'db': 'pubmed', 'term': query, 'retmode': 'json', 'retmax': limit,
                        'sort': 'relevance', 'tool': 'PCSK9Lab', **dated}, log=logs))['esearchresult']
                    if found.get('ERROR') or found.get('errorlist'):
                        raise ValueError('PubMed did not accept the query')
                    ids = found['idlist']
                    count = int(found['count'])
                    rows = []
                    if ids:
                        root = xml(fetch(client, f'{EUTILS}/efetch.fcgi', params={
                            'db': 'pubmed', 'id': ','.join(ids), 'retmode': 'xml', 'tool': 'PCSK9Lab'}, log=logs))
                        for article in root.findall('.//PubmedArticle'):
                            # Reference-list IDs belong to other papers, never this publication.
                            identifiers = {n.attrib.get('IdType'): text(n) for n in article.findall('./PubmedData/ArticleIdList/ArticleId')}
                            pmid = text(article.find('./MedlineCitation/PMID'))
                            rows.append({'pmid': pmid, 'pmcid': identifiers.get('pmc'), 'doi': identifiers.get('doi'),
                                'title': text(article.find('.//ArticleTitle')),
                                'abstract': '\n'.join(text(n) for n in article.findall('.//AbstractText')),
                                'journal': text(article.find('.//Journal/Title')),
                                'publication_date': text(article.find('.//JournalIssue/PubDate')),
                                'url': f'https://pubmed.ncbi.nlm.nih.gov/{pmid}/', 'provider': provider})
                    returned = len(rows)
                else:
                    dated_query = (f'({query}) AND FIRST_PDATE:[{start_date or "0001-01-01"} TO {end_date or "3000-12-31"}]'
                                   if bounds else query)
                    data = json.loads(fetch(client, f'{EPMC}/search', params={
                        'query': dated_query, 'format': 'json', 'resultType': 'core', 'pageSize': limit,
                        'cursorMark': '*'}, log=logs))
                    count = int(data['hitCount'])
                    rows = [{'pmid': r.get('pmid'), 'pmcid': r.get('pmcid'), 'doi': r.get('doi'),
                             'title': r.get('title', ''), 'abstract': r.get('abstractText', ''),
                             'journal': r.get('journalInfo', {}).get('journal', {}).get('title'),
                             'publication_date': r.get('firstPublicationDate'),
                             'url': f"https://europepmc.org/article/{r['source']}/{r['id']}",
                             'is_open_access': r.get('isOpenAccess'), 'provider': provider,
                             'provider_id': r['id'], 'provider_source': r['source']}
                            for r in data.get('resultList', {}).get('result', [])]
                    returned = len(rows)
                providers[provider] = {'status': 'complete' if count == returned else 'capped',
                                       'total_hits': count, 'returned': returned, 'limit': limit}
                results.extend(rows)
            except (ValueError, KeyError, TypeError, ET.ParseError, httpx.HTTPError):
                providers[provider] = {'status': 'failed', 'message': 'Retrieval failed; inspect the retained response log and retry.'}
        merged = []
        for row in results:
            existing = next((r for r in merged if any(row.get(k) and r.get(k) and
                row[k].lower() == r[k].lower() for k in ('pmid', 'pmcid', 'doi'))), None)
            if existing:
                existing['retrieved_from'].append(row)
                for key, value in row.items():
                    if not existing.get(key) and value:
                        existing[key] = value
            else:
                merged.append({**row, 'retrieved_from': [dict(row)]})
        return {'query': query, 'publication_date_bounds': bounds, 'retrieved_at': now(), 'providers': providers,
                'publications': merged, 'coverage': 'First bounded relevance page per provider; not a systematic or exhaustive review.',
                'response_log': logs}
    finally:
        if owned:
            client.close()


def parse_jats(raw):
    root = xml(raw)
    passages = []

    def add(locator, kind, value):
        value = value.strip()
        # Preserve source substrings and mark split offsets, including long tables.
        for offset in range(0, len(value), 2400):
            part = value[offset:offset+2400]
            passages.append({'id': f'P{len(passages)+1}', 'locator': f'{locator}; character {offset}',
                             'kind': kind, 'text': part})
        if len(passages) > 1500:
            raise ValueError('Article exceeds the supported passage count')

    def walk(node, path):
        for child in node:
            tag = child.tag.rsplit('}', 1)[-1]
            if tag == 'sec':
                heading = text(child.find('title')) or child.attrib.get('sec-type', 'Section')
                walk(child, f'{path} / {heading}')
            elif tag == 'table-wrap':
                label = text(child.find('label')) or child.attrib.get('id', 'Table')
                rows = [' | '.join(text(cell) for cell in list(row)) for row in child.findall('.//tr')]
                caption, foot = text(child.find('caption')), text(child.find('table-wrap-foot'))
                add(f'{path} / {label}', 'table', '\n'.join([caption, *rows, foot]))
            elif tag == 'fig':
                add(f"{path} / {text(child.find('label')) or 'Figure'}", 'figure_caption', text(child.find('caption')))
            elif tag == 'p':
                add(path, 'paragraph', text(child))
            elif tag not in {'ref-list', 'title'}:
                walk(child, path)

    abstract = root.find('.//article-meta/abstract')
    if abstract is not None:
        add('Abstract', 'abstract', text(abstract))
    body = root.find('.//body')
    if body is not None:
        walk(body, 'Full text')
    if not passages:
        raise ValueError('No article text found in XML')
    return {'passages': passages, 'parser': 'jats-etree-v1',
            'text_scope': 'full_text' if body is not None else 'abstract_only',
            'article_ids': {n.attrib.get('pub-id-type'): text(n) for n in root.findall('.//article-meta/article-id')},
            'license': text(root.find('.//permissions')) or 'Not supplied; verify reuse terms',
            'limitations': ([] if body is not None else ['Repository XML contains abstract only; methods and tables are unavailable.']) +
                           ['Figure pixels and supplementary files are not extracted.',
                            'Table row/column associations and all measurements require source verification.']}


def parse_pdf(raw):
    if len(raw) > MAX_BYTES or not raw.startswith(b'%PDF-'):
        raise ValueError('Expected a PDF smaller than 25 MB; HTML/challenge pages are not accepted')
    try:
        result = subprocess.run([sys.executable, '-m', 'cvti.literature_pdf'], input=raw,
                                capture_output=True, timeout=30)
        if result.returncode or len(result.stdout) > 8_000_000:
            raise ValueError('PDF processing failed or exceeded its output limit')
        parsed = json.loads(result.stdout)
        if 'error' in parsed:
            raise ValueError(parsed['error'])
        return parsed
    except subprocess.TimeoutExpired as exc:
        raise ValueError('PDF processing exceeded 30 seconds; upload a smaller source extract with page attribution') from exc


def _parse_pdf_local(raw):
    import pdfplumber
    if len(raw) > MAX_BYTES or not raw.startswith(b'%PDF-'):
        raise ValueError('Expected a PDF smaller than 25 MB; HTML/challenge pages are not accepted')
    passages = []
    try:
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            if len(pdf.pages) > 100:
                raise ValueError('PDF exceeds the 100-page limit')
            for page_no, page in enumerate(pdf.pages, 1):
                value = page.extract_text() or ''
                for offset in range(0, len(value), 2400):
                    passages.append({'id': f'P{len(passages)+1}', 'locator': f'PDF page {page_no}; character {offset}',
                                     'kind': 'page_text', 'text': value[offset:offset+2400]})
                # Avoid interpreting dense chart vectors as thousands of table edges.
                tables = page.extract_tables() if len(page.edges) < 1000 else []
                for number, table in enumerate(tables, 1):
                    value = '\n'.join(' | '.join(cell or '' for cell in row) for row in table)
                    for offset in range(0, len(value), 2400):
                        passages.append({'id': f'P{len(passages)+1}',
                            'locator': f'PDF page {page_no}, table {number}; character {offset}',
                            'kind': 'table', 'text': value[offset:offset+2400]})
                if len(passages) > 1500:
                    raise ValueError('PDF exceeds the supported passage count')
                page.close()
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError('PDF cannot be parsed; obtain a readable unencrypted original') from exc
    if not passages:
        raise ValueError('No selectable PDF text; scanned/figure-only sources need manual transcription or OCR')
    return {'passages': passages, 'parser': f'pdfplumber-{version("pdfplumber")}',
            'license': 'Verify publisher/repository reuse terms; access does not establish reuse permission.',
            'limitations': ['No OCR or figure-image transcription. Methods/table layout require visual verification.',
                            'Automatic table grids are skipped on pages with 1000 or more drawing edges; page text is retained.']}


def _pmc_file(client, pmcid, kind, logs):
    """Anonymous HTTPS reads from NLM's public dataset; no AWS account/services.

    Legacy oa.fcgi/FTP were retired in August 2026. Multiple deposited versions
    need explicit selection; never silently prefer a higher version number.
    """
    base = 'https://pmc-oa-opendata.s3.amazonaws.com'
    listing = xml(fetch(client, base + '/', params={'list-type': '2', 'prefix': pmcid + '.',
                  'delimiter': '/', 'max-keys': '20'}, log=logs))
    prefixes = [text(n) for n in listing.iter() if n.tag.rsplit('}', 1)[-1] == 'Prefix'
                and re.fullmatch(re.escape(pmcid) + r'\.[0-9]+/', text(n))]
    if len(prefixes) != 1:
        raise ValueError('PMC dataset version is missing or ambiguous; upload the explicitly selected source PDF')
    prefix = prefixes[0]
    metadata_raw = fetch(client, f'{base}/{prefix}{prefix.rstrip("/")}.json', log=logs)
    metadata = json.loads(metadata_raw)
    if metadata.get('pmcid') != pmcid:
        raise ValueError('PMC dataset metadata identity mismatch')
    location = metadata.get(f'{kind}_url')
    if not location:
        raise ValueError('PMC dataset does not offer this full-text format')
    if location.startswith('s3://pmc-oa-opendata/'):
        location = base + '/' + location.removeprefix('s3://pmc-oa-opendata/')
    parts = urlsplit(location)
    if (parts.scheme != 'https' or parts.netloc != 'pmc-oa-opendata.s3.amazonaws.com'
            or not parts.path.startswith('/' + prefix) or '..' in parts.path.split('/')):
        raise ValueError('PMC file URL left the selected public article prefix')
    raw = fetch(client, location, log=logs)
    expected = parse_qs(parts.query).get('md5', [None])[0]
    if expected and hashlib.md5(raw).hexdigest() != expected:
        raise ValueError('PMC publisher file checksum mismatch')
    return raw, {'repository_file_url': location, 'repository_metadata': metadata,
                 'repository_metadata_sha256': sha(metadata_raw), 'repository_prefix': prefix}


def download(pmcid, kind, client=None):
    if not re.fullmatch(r'PMC[0-9]+', pmcid):
        raise ValueError('A valid PMC identifier is required for repository full text')
    if kind not in {'xml', 'pdf'}:
        raise ValueError('Choose XML or PDF')
    url = (f'{EPMC}/{pmcid}/fullTextXML' if kind == 'xml' else
           f'https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/pdf/')
    owned = client is None
    client = client or public_client()
    logs = []
    try:
        parser = parse_jats if kind == 'xml' else parse_pdf
        package_info = {}
        try:
            raw = fetch(client, url, log=logs)
            parsed = parser(raw)
        except (ValueError, httpx.HTTPError, ET.ParseError):
            if kind == 'xml':
                try:
                    raw = fetch(client, f'{EUTILS}/efetch.fcgi', params={'db': 'pmc',
                                'id': pmcid.removeprefix('PMC'), 'retmode': 'xml', 'tool': 'PCSK9Lab'}, log=logs)
                    parsed = parser(raw)
                    package_info['repository_file_url'] = f'{EUTILS}/efetch.fcgi?db=pmc&id={pmcid.removeprefix("PMC")}&retmode=xml'
                except (ValueError, httpx.HTTPError, ET.ParseError):
                    raw, package_info = _pmc_file(client, pmcid, kind, logs)
                    parsed = parser(raw)
            else:
                raw, package_info = _pmc_file(client, pmcid, kind, logs)
                parsed = parser(raw)
        if kind == 'xml':
            identifiers = parsed['article_ids']
            identifier = identifiers.get('pmc') or identifiers.get('pmcid')
            if identifier and identifier.removeprefix('PMC') != pmcid.removeprefix('PMC'):
                raise ValueError('Downloaded article identity does not match the selected publication')
        return raw, {**parsed, **package_info, 'format': kind, 'url': url, 'retrieved_at': now(),
                     'transport': [{k: v for k, v in log.items() if k != 'body_base64'} for log in logs]}
    finally:
        if owned:
            client.close()
