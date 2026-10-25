# Image de l'agent de dépannage : Claude Code (binaire natif) + Python 3 + git. Rien d'autre (ni docker, ni curl, ni sops).
# Construite sur le Mini PC par : scripts/compose-up.sh agent up -d --build
# Version de Claude Code : CLAUDE_CODE_VERSION dans compose.yaml (figée ; suivie par Renovate). Mise à jour automatique désactivée.

# ---- Étape 1 : récupérer le binaire natif de Claude Code depuis npm (paquet de la plateforme linux-x64)
FROM node:22-trixie-slim AS claude
ARG CLAUDE_CODE_VERSION
RUN test -n "$CLAUDE_CODE_VERSION" \
 && npm install --global --no-fund --no-audit --loglevel=error "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" \
 && cp "$(readlink -f "$(command -v claude)")" /claude \
 && /claude --version

# ---- Étape 2 : image finale minimale
FROM debian:trixie-slim
ARG CLAUDE_CODE_VERSION
LABEL org.opencontainers.image.title="agent-homelab" \
      org.opencontainers.image.description="Agent de dépannage du homelab (Claude Code, abonnement Pro)" \
      claude-code.version="${CLAUDE_CODE_VERSION}"

RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 git ca-certificates tzdata tini \
 && rm -rf /var/lib/apt/lists/*

COPY --from=claude /claude /usr/local/bin/claude
COPY agent/ /opt/agent/

# Les outils de Claude sont des liens vers outils.py (le nom appelé choisit la commande)
RUN chmod 0755 /opt/agent/agent.py /opt/agent/outils.py \
 && for o in conteneurs conteneur journaux evenements loki prom hote historique action; do \
      ln -s /opt/agent/outils.py "/usr/local/bin/$o"; \
    done \
 && chmod -R a-w /opt/agent

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/home/agent \
    DISABLE_AUTOUPDATER=1 \
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1

USER 1000:1000
WORKDIR /data/depot
EXPOSE 8080
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python3", "/opt/agent/agent.py", "serveur"]
