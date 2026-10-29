FROM medbal-py-base

WORKDIR /app/services/sim-hospital
COPY services/sim-hospital /app/services/sim-hospital
RUN uv pip install --system -e /app/services/sim-hospital

EXPOSE 8100
CMD ["sh", "-c", "uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8100}"]

