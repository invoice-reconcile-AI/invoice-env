FROM python:3.12-slim

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY server/ ./server/
COPY frontend/ ./frontend/

# Expose FastAPI port
EXPOSE 7860

# Start the server
CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "7860"]
