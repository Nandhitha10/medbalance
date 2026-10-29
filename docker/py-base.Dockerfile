FROM python:3.12-slim

# Install system dependencies and uv
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv from official binary
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy and install medbal_common shared library
WORKDIR /app/libs/medbal_common
COPY libs/medbal_common /app/libs/medbal_common
RUN uv pip install --system -e /app/libs/medbal_common

WORKDIR /app
