FROM medbal-py-base

WORKDIR /app/services/genai
COPY services/genai /app/services/genai
COPY prompts /app/prompts
RUN uv pip install --system -e /app/services/genai

EXPOSE 8003
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8003"]
