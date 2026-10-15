FROM python:3.12-slim

WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/opt/cvti-venv \
    UV_LINK_MODE=copy \
    PATH=/opt/cvti-venv/bin:$PATH \
    PYTHONUNBUFFERED=1

RUN python -m pip install --no-cache-dir uv==0.13.1
COPY pyproject.toml uv.lock README.md alembic.ini dashboard.py ./
COPY src ./src
COPY migrations ./migrations
COPY fixtures ./fixtures
COPY .streamlit ./.streamlit
RUN uv sync --frozen --no-dev --no-editable

EXPOSE 8000
CMD ["uvicorn", "cvti.api:app", "--host", "0.0.0.0", "--port", "8000"]
