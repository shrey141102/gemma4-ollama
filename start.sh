#!/bin/bash
set -e

echo "============================================"
echo "  Starting Ollama + Gemma4 E2B on Render"
echo "============================================"

# 1. Start Ollama server in the background
echo "[1/3] Starting Ollama server..."
ollama serve &
OLLAMA_PID=$!

# Wait for Ollama to be ready
echo "       Waiting for Ollama to be ready..."
for i in $(seq 1 60); do
    if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo "       Ollama is ready!"
        break
    fi
    if [ $i -eq 60 ]; then
        echo "ERROR: Ollama failed to start after 60 seconds"
        exit 1
    fi
    sleep 1
done

# 2. Pull the model (skip if already cached via persistent disk)
echo "[2/3] Pulling gemma4:e2b model..."
if ollama list | grep -q "gemma4:e2b"; then
    echo "       Model already cached, skipping download."
else
    echo "       Downloading model (this takes a few minutes on first deploy)..."
    ollama pull gemma4:e2b
    echo "       Model downloaded successfully!"
fi

# 3. Pre-warm the model (load it into memory)
echo "[3/3] Pre-warming model..."
curl -s http://localhost:11434/api/chat -d '{
    "model": "gemma4:e2b",
    "messages": [{"role": "user", "content": "hi"}],
    "stream": false,
    "options": {"num_ctx": 8192}
}' > /dev/null 2>&1 || true
echo "       Model loaded into memory!"

echo "============================================"
echo "  Starting API server on port ${PORT:-8000}"
echo "============================================"

# 4. Start the FastAPI app (Render injects $PORT)
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
