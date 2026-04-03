FROM gcr.io/distroless/python3-debian13:nonroot AS runtime-base

FROM python:3.13-slim AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade "pip>=25.3"
RUN pip install --no-cache-dir --target /opt/python -r requirements.txt

COPY . /app

FROM runtime-base

WORKDIR /app

COPY --from=builder /opt/python /opt/python
COPY --from=builder /app /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/opt/python:/app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["/usr/bin/python3", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=2)"]

ENTRYPOINT []

CMD ["/usr/bin/python3", "-m", "uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000"]
