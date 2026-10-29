FROM medbal-py-base

WORKDIR /app/services/forecast
COPY services/forecast /app/services/forecast
RUN uv pip install --system -e /app/services/forecast

EXPOSE 8004
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8004"]
