# Translation proxy: Anthropic-format requests in, any OpenAI-compatible local model server out.
FROM python:3.12-slim
ARG LITELLM_VERSION=1.101.0
RUN pip install --no-cache-dir "litellm[proxy]==${LITELLM_VERSION}"
# The proxy needs no root rights. A fixed UID keeps the container user the same on every rebuild.
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin litellm
WORKDIR /app
COPY hoist_system.py litellm.yaml ./
ENV HOME=/tmp
USER 10001:10001
EXPOSE 4000
# python:3.12-slim has no curl, so the check uses the standard library.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:4000/health/liveliness', timeout=4)"]
CMD ["litellm", "--config", "/app/litellm.yaml", "--host", "0.0.0.0", "--port", "4000"]
