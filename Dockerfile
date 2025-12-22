FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    inotify-tools \
    jhead \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY build.py .
COPY templates/ templates/
COPY favicon.svg .

# Copy watcher script
COPY docker-watcher.sh .
RUN chmod +x docker-watcher.sh

# Create directories for volumes
RUN mkdir -p /app/originals /app/site

# Environment variables with defaults
ENV ROW_HEIGHT=300
ENV PREVIEW_HEIGHT=400
ENV PRELOAD_COUNT=20
ENV WORKERS=4
ENV WATCH_DELAY=5
ENV RUN_ON_STARTUP=true
ENV LOG_LEVEL=INFO
ENV RENAME=false
ENV TITLE="[photostream]"
ENV DESCRIPTION=""
ENV FOOTER=""
ENV LINK1_TITLE=""
ENV LINK1_URL=""
ENV LINK2_TITLE=""
ENV LINK2_URL=""
ENV LINK3_TITLE=""
ENV LINK3_URL=""
ENV GEOCODE=false

# Use the watcher script as entrypoint
ENTRYPOINT ["./docker-watcher.sh"]