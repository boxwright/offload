# The Offload sandbox: the container every worker call and every test run happens in.
# Python for the project's tests, Claude Code for the workers, and an outbound firewall that is raised
# by root before the worker starts. The worker then runs with no sudo and no capabilities, so it cannot
# change the rules.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      bash ca-certificates curl git iptables ipset iproute2 util-linux \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir pytest pyyaml

RUN useradd --create-home --shell /bin/bash worker \
    && mkdir -p /workspace /home/worker/.claude \
    && chown -R worker:worker /workspace /home/worker/.claude

# Claude Code, from Anthropic's installer, pinned to a version that Offload's jobs were proven on. Downloaded at
# build time; it is not part of this repository. Raise the pin on purpose, after a test job on the new version:
#   docker build --build-arg CLAUDE_CODE_VERSION=<version> -t offload-sandbox:latest sandbox/
ARG CLAUDE_CODE_VERSION=2.1.278
USER worker
RUN curl -fsSL https://claude.ai/install.sh | bash -s -- "$CLAUDE_CODE_VERSION" \
    && /home/worker/.local/bin/claude --version | grep -F "$CLAUDE_CODE_VERSION"
USER root

COPY firewall.sh /usr/local/sbin/offload-firewall
COPY entry.sh /usr/local/sbin/offload-entry
RUN chmod 0755 /usr/local/sbin/offload-firewall /usr/local/sbin/offload-entry
ENV CLAUDE_CONFIG_DIR=/home/worker/.claude DISABLE_AUTOUPDATER=1
WORKDIR /workspace
ENTRYPOINT ["/usr/local/sbin/offload-entry"]
