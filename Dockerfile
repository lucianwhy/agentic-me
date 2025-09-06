# syntax=docker/dockerfile:1.7
FROM python:3.12

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

# Use the token only via a secret mount during this RUN.
# Nothing is persisted in layers or ENV.
# Only install guardrails if token is provided
RUN --mount=type=secret,id=guardrails_token \
    if [ -f /run/secrets/guardrails_token ] && [ -s /run/secrets/guardrails_token ]; then \
        echo "Installing Guardrails AI with provided token..." && \
        guardrails configure --token "$(cat /run/secrets/guardrails_token)" --disable-metrics --disable-remote-inferencing && \
        guardrails hub install hub://guardrails/toxic_language --quiet && \
        guardrails hub install hub://guardrails/reading_time --quiet && \
        guardrails hub install hub://guardrails/profanity_free --quiet; \
    else \
        echo "No Guardrails token provided - skipping Guardrails AI installation"; \
    fi

# Create application user and directories
RUN useradd --create-home --shell /bin/bash app && \
    mkdir -p /app/logs /app/data/vector_db && \
    chown -R app:app /app

RUN mkdir -p /app/logs && \
    chown -R app:app /app/logs && \
    chmod 755 /app/logs

ENV LOG_DIR=/app/logs
ENV LOG_LEVEL=INFO
ENV DOCKER_CONTAINER=true

COPY . .

VOLUME ["/app/logs", "/app/data/vector_db"]

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
