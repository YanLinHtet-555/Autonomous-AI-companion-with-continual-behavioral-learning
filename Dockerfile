# AI Companion — Docker image (runs the AI brain only)
# The monitoring layer (monitoring_agent.py) runs NATIVELY on the host.
#
# Build:  docker build -t ai-companion .
# Run:    docker-compose up   (see docker-compose.yml)

FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# ── System deps ───────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.11 \
        python3.11-dev \
        python3-pip \
        build-essential \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Make python3.11 the default
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 \
 && update-alternatives --install /usr/bin/pip    pip    /usr/bin/pip3      1

# ── Python deps ───────────────────────────────────────────────────────────────
WORKDIR /app

COPY requirements.docker.txt ./
RUN pip install --upgrade pip \
 && pip install -r requirements.docker.txt

# Install PyTorch with CUDA 12.1 support
RUN pip install torch torchvision torchaudio \
        --index-url https://download.pytorch.org/whl/cu121

# ── Application code ──────────────────────────────────────────────────────────
# Copy everything except host-only monitoring and Windows-specific files
COPY api/           ./api/
COPY companion/     ./companion/
COPY learning/      ./learning/
COPY memory/        ./memory/
COPY model/         ./model/
COPY privacy/       ./privacy/
COPY security/      ./security/
COPY summarizer/    ./summarizer/
COPY config.py      ./
COPY setup.py       ./

# Create data directory (will be overridden by volume mount at runtime)
RUN mkdir -p /app/data/checkpoints /app/data/logs

# ── Runtime ───────────────────────────────────────────────────────────────────
EXPOSE 8000

# Healthcheck — polls /health every 30s, gives 5 min on startup for model load
HEALTHCHECK --interval=30s --timeout=10s --start-period=300s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["python", "-m", "uvicorn", "api.server:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--no-access-log"]
