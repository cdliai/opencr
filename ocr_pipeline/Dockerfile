FROM python:3.12-slim

# System dependencies
RUN apt-get update && apt-get install -y \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (cached layer)
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy application code into the correct package directory.
# Build context is ./ocr_pipeline but imports use "from ocr_pipeline.xxx",
# so files must live at /app/ocr_pipeline/ for PYTHONPATH=/app to work.
COPY . /app/ocr_pipeline/

ENV PYTHONPATH=/app

EXPOSE 39672

CMD ["uvicorn", "ocr_pipeline.main:app", "--host", "0.0.0.0", "--port", "39672", "--no-access-log"]
