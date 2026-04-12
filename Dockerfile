FROM python:3.12-slim

WORKDIR /app

COPY . .

RUN apt-get update && apt-get install -y nginx && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r requirements.txt supervisor

# This file runs both FastAPI and Streamlit
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

EXPOSE 7860

CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
