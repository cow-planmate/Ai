# Use a lightweight Python base image
FROM python:3.12-slim

# Avoid buffering stdout/stderr
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8010 \
    PYTHONPATH=/app

# Set the working directory
WORKDIR /app

# Install system dependencies (if any are needed in the future)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
 && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY . /app

# Install Python dependencies
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn[standard] \
    python-dotenv \
    python-dateutil \
    requests \
    google-generativeai

# Expose the application port
EXPOSE ${PORT}

# Start the FastAPI application via uvicorn
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8010}"]
