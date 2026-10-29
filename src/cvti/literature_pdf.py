"""Disposable PDF parsing process; parent enforces byte/page/time/output bounds."""
import json
import sys

from cvti.literature_sources import MAX_BYTES, _parse_pdf_local

if __name__ == '__main__':
    try:
        result = _parse_pdf_local(sys.stdin.buffer.read(MAX_BYTES+1))
    except Exception as exc:
        result = {'error': str(exc)[:500]}
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))
