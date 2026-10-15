FROM python:3.12-slim

WORKDIR /app

# Install dependencies first for layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Project code, reading logic, config/prompts/texts, and helper scripts.
COPY manage.py .
COPY academic_reading_django/ ./academic_reading_django/
COPY reading/ ./reading/
COPY accounts/ ./accounts/
COPY config.yaml prompts.yaml ./
COPY texts/ ./texts/
COPY docker/entrypoint.sh /app/docker/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/docker/entrypoint.sh"]
