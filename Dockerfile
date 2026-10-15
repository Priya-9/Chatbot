FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY locales ./locales
COPY knowledge ./knowledge
COPY prompts ./prompts
COPY demo ./demo
COPY scripts ./scripts

# uid 1000: client folders mounted from the host are chown'ed to it by deploy/scripts/new-client.sh
RUN useradd --create-home --uid 1000 bot && mkdir -p data && chown -R bot /app
USER bot

EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
# Only Caddy can reach the container, so its X-Forwarded-* headers are trusted.
# Single worker keeps per-user message ordering simple; scale horizontally behind a sticky load balancer.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
