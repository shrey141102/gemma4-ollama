"""
Configuration — all settings loaded from environment variables.
"""

import os

# Ollama connection
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

# Model settings
MODEL_NAME = os.getenv("MODEL_NAME", "gemma4:e2b")
NUM_CTX = int(os.getenv("NUM_CTX", "8192"))

# Optional API key for basic auth (set in Render env vars)
API_KEY = os.getenv("API_KEY", "")
