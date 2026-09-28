#!/usr/bin/env bash
set -euo pipefail

if ! command -v ollama >/dev/null 2>&1; then
  echo "Ollama is not installed. Please install it and rerun this script."
  exit 1
fi

OLLAMA_HOST="${OLLAMA_HOST:-http://localhost:11434}"
OLLAMA_MODEL="${OLLAMA_MODEL:-llama3.2:3b}"

export OLLAMA_HOST
ollama pull "$OLLAMA_MODEL"
ollama pull nomic-embed-text

echo "Ollama model ready: $OLLAMA_MODEL"
