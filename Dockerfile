FROM python:3.13.5-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN groupadd --system taxicarga && useradd --system --gid taxicarga --home-dir /app taxicarga
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=taxicarga:taxicarga . .
RUN mkdir -p /app/staticfiles /app/datos_privados/media && chown -R taxicarga:taxicarga /app/staticfiles /app/datos_privados
USER taxicarga
EXPOSE 8000
STOPSIGNAL SIGTERM
CMD ["gunicorn", "config.wsgi:application", "--bind=0.0.0.0:8000", "--workers=3", "--timeout=60", "--graceful-timeout=30", "--access-logfile=-", "--error-logfile=-"]
