# 🚀 Ollama + Gemma4 E2B on Render.com

Run your own private LLM in the cloud with a chat UI and REST API.

## What's Inside

| File           | Purpose                                           |
|----------------|---------------------------------------------------|
| `Dockerfile`   | Installs Ollama + Python deps                     |
| `start.sh`     | Boots Ollama → pulls model → starts API server    |
| `server.py`    | FastAPI app with chat UI + REST API               |
| `render.yaml`  | Render blueprint (one-click infra-as-code)        |

## Deploy to Render

1. **Push this folder to a GitHub repo**
2. **Go to [render.com/new](https://render.com/new)** → "Blueprint" → connect your repo
3. **Render reads `render.yaml`** and provisions everything automatically
4. **First deploy takes ~5-8 min** (downloads the 7GB model — cached on disk after that)
5. Visit `https://your-service.onrender.com` → chat UI is live!

### Or deploy manually:
1. New → Web Service → Docker → connect repo
2. Set plan to **Pro Plus** (8GB RAM, 4 vCPU)
3. Add a **Persistent Disk** (10GB, mount at `/root/.ollama`)
4. Set env vars: `MODEL_NAME=gemma4:e2b`, `NUM_CTX=8192`
5. Deploy!

## API Usage

### Chat (multi-turn)
```bash
curl -X POST https://your-service.onrender.com/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "Explain quantum computing in simple terms"}
    ],
    "stream": false
  }'
```

### Quick question
```bash
curl "https://your-service.onrender.com/ask?q=What+is+the+speed+of+light?"
```

### Streaming
```bash
curl -N -X POST https://your-service.onrender.com/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Write a haiku about code"}],
    "stream": true
  }'
```

### With API key (if you set one)
```bash
curl -H "Authorization: Bearer my-secret-key" \
  "https://your-service.onrender.com/ask?q=hello"
```

## Memory Budget (8GB)

| Component       | RAM Usage   |
|-----------------|-------------|
| Gemma4 E2B (Q4) | ~3.4 GB    |
| KV Cache (8K)   | ~0.5 GB    |
| Ollama runtime   | ~0.8 GB    |
| FastAPI + OS     | ~0.5 GB    |
| **Headroom**     | **~2.8 GB** |

If you bump to **Pro Max (16GB / $225/mo)**, you can:
- Increase `NUM_CTX` to 32768 (32K context)
- Or run `gemma4:e4b` for better quality

## Important Notes

- **CPU-only inference**: Render doesn't offer GPUs on standard plans. Expect 5-20 second response times depending on output length. Perfectly usable for personal/team chatbots.
- **Persistent disk**: The `render.yaml` includes a 10GB disk so you don't re-download the model on every deploy.
- **Spin-down**: Render's free/starter tiers spin down on inactivity. Pro Plus stays always-on.
- **Security**: Set the `API_KEY` env var in Render dashboard to protect your endpoint.

## Cost

~$175/month for the Pro Plus instance + ~$2.50/month for the 10GB persistent disk.

**Cheaper alternatives** if $175/mo is too much:
- [Railway](https://railway.app) — similar Docker deploy, pay-per-use
- [Fly.io](https://fly.io) — 8GB machines from ~$60/mo
- A Hetzner VPS (€20/mo for 16GB ARM) — most cost-effective
