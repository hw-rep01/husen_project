# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

ARG INSTALL_ML=false

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --home-dir /app app

COPY requirements.txt requirements-ml.txt ./

RUN pip install --upgrade pip \
    && if [ "$INSTALL_ML" = "true" ]; then \
         pip install --index-url https://download.pytorch.org/whl/cpu torch==2.5.1 \
         && pip install -r requirements-ml.txt; \
       fi \
    && pip install -r requirements.txt

COPY . .

RUN mkdir -p /app/storage/materials && chown -R app:app /app/storage

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers", "--forwarded-allow-ips=*"]