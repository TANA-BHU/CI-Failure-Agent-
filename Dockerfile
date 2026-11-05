FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

COPY config.yaml ./
COPY runbooks ./runbooks

# Run as non-root
RUN useradd -m app && mkdir -p /app/metrics && chown -R app /app
USER app

EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/healthz')" || exit 1
CMD ["uvicorn", "ci_triage.api:app", "--host", "0.0.0.0", "--port", "8000"]
