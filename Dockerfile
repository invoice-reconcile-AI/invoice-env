FROM python:3.11-slim

WORKDIR /app

# Install dependencies + nginx/supervisor
RUN apt-get update && apt-get install -y nginx supervisor && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Expose the standard HF port
EXPOSE 7860

# Run supervisor to manage nginx, api, and ui
CMD ["/usr/bin/supervisord", "-c", "/app/supervisord.conf"]
