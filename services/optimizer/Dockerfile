FROM medbal-py-base

WORKDIR /app/services/optimizer
COPY services/optimizer /app/services/optimizer
RUN uv pip install --system -e /app/services/optimizer

EXPOSE 8005
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8005"]

