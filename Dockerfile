FROM python:3.11-slim

# Install system deps
RUN apt-get update && apt-get install -y curl procps && rm -rf /var/lib/apt/lists/*

# Install Ollama
RUN curl -fsSL https://ollama.com/install.sh | sh

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . /app
WORKDIR /app

# Ollama config — keep it lean for 8GB RAM
ENV OLLAMA_HOST=0.0.0.0:11434
ENV OLLAMA_NUM_PARALLEL=1
ENV OLLAMA_MAX_LOADED_MODELS=1
ENV OLLAMA_KEEP_ALIVE=5m

# Expose the web UI / API port (Render uses $PORT)
EXPOSE 8000

# Start everything via the entrypoint script
RUN chmod +x /app/start.sh
CMD ["/app/start.sh"]
