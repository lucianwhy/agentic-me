#!/bin/bash

# Start Ollama in the background.
/bin/ollama serve &
# Record Process ID.
pid=$!

# Pause for Ollama to start.
sleep 5

MODEL_TO_PULL="${OLLAMA_MODELS}"
echo "Retrieve model: $MODEL_TO_PULL ..."
ollama pull "$MODEL_TO_PULL"
ollama start
echo "Done!"

# Wait for Ollama process to finish.
wait $pid
