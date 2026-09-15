FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock && useradd --uid 1000 --create-home fitness
COPY . .
RUN SECRET_KEY=build-only-not-for-runtime DEBUG=true python manage.py collectstatic --noinput && mkdir -p /app/media && chown 1000:1000 /app/media
USER 1000:1000
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "2", "--timeout", "90", "--access-logfile", "-", "--error-logfile", "-", "--limit-request-line", "4094", "--limit-request-fields", "50", "--limit-request-field_size", "8190"]
