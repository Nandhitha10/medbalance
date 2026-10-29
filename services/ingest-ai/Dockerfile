FROM medbal-py-base

WORKDIR /app/services/ingest-ai
COPY services/ingest-ai /app/services/ingest-ai
RUN uv pip install --system -e /app/services/ingest-ai

EXPOSE 8002
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8002"]

