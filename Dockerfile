FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Install build deps and runtime deps
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir gunicorn

# Copy application
COPY . .

# Create non-root user
RUN adduser --disabled-password --gecos '' appuser || true
USER appuser

EXPOSE 5000

# Run with Gunicorn for production-like server
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
