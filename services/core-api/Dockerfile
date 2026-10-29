FROM medbal-py-base

WORKDIR /app/services/core-api
COPY services/core-api /app/services/core-api
RUN uv pip install --system -e /app/services/core-api

EXPOSE 8001
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001"]
