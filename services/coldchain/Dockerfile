FROM medbal-py-base

WORKDIR /app/services/coldchain
COPY services/coldchain /app/services/coldchain
RUN uv pip install --system -e /app/services/coldchain

EXPOSE 8006
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8006"]
