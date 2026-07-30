#!/bin/bash
# Start Ollama server with correct library paths for RTX 5050
export LD_LIBRARY_PATH=$HOME/.local/lib/ollama:$HOME/.local/lib/ollama/cuda_v13
export OLLAMA_HOST=127.0.0.1:11434
exec $HOME/.local/bin/ollama serve
