FROM medbal-py-base

WORKDIR /app/services/sensors
COPY services/sensors /app/services/sensors
RUN uv pip install --system -e /app/services/sensors

EXPOSE 8105
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8105"]
