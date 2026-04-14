FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Expose the standard HF port
EXPOSE 7860

# Run FastAPI directly
CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "7860"]
