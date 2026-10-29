# SecVerify Agent — container image (any Docker-capable platform)
# Build:  docker build -t secverify-agent .
# Run:    docker run -p 8501:8501 -e INTERN_API_KEY= secverify-agent
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 STREAMLIT_SERVER_HEADLESS=true

COPY pyproject.toml README.md ./
COPY src ./src
COPY policies ./policies
COPY demos ./demos
COPY evaluation ./evaluation
COPY scripts ./scripts
COPY app.py ./

RUN pip install --no-cache-dir -e . && pip install --no-cache-dir pytest

# unprivileged runtime user; artifacts stay inside /app/artifacts
RUN useradd -m appuser && mkdir -p /app/artifacts && chown -R appuser /app
USER appuser

EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health')" || exit 1

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
