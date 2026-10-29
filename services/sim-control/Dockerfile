FROM medbal-py-base

WORKDIR /app/services/sim-control
COPY services/sim-control /app/services/sim-control
RUN uv pip install --system -e /app/services/sim-control

EXPOSE 8100
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8100"]

