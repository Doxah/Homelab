# 15 — Agent de dépannage (Claude Code)

Un agent IA surveille le Mini PC : quand un conteneur plante, il diagnostique, relance ce qui est autorisé,
propose le correctif en Pull Request et envoie un rapport. Chaque matin, il fait le bilan de la veille.
Installation et réglages : [compose/agent/README.md](../compose/agent/README.md).

## Fonctionnement
```
                   ┌────────────────────────── conteneur agent (aucun droit d'écriture sur l'hôte) ─────────────────────┐
Alertmanager ─────►│ agent.py : filtre, regroupe, anti-rebond, plafond/jour                                             │
healthchecks ─────►│   └─► claude -p  (abonnement Pro, Sonnet, permissions « dontAsk »)                                │
                   │         lit   : socket-proxy-agent (API Docker GET filtrée), Loki, Prometheus, clone public du dépôt  │
                   │         agit  : outil « action » ──► data/actions/demandes/<id>.demande                            │
                   │         corrige : fichiers du clone ──► agent.py vérifie ──► branche agent/<id> ──► PR GitHub        │
                   │   └─► rapport : data/rapports/<id>.md + ntfy (homelab-agent) + métriques homelab_agent_*           │
                   └───────────────────────────────────────────────────────────────────────────────────────────────────┘
hôte (cron) : scripts/agent-actions.sh ── vérifie compose/agent-actions.txt ──► scripts/compose-up.sh <stack> restart|up
```

| Déclencheur | Ce qui se passe |
|---|---|
| `ConteneurDisparu`, `ConteneurRedemarreEnBoucle`, `ConteneurTueOOM`, `ConteneurProcheLimiteMemoire` | diagnostic du conteneur |
| `ServiceInjoignable`, `TunnelCloudflareCoupe`, `TraefikErreurs5xx` | diagnostic de la chaîne Traefik / tunnel / service |
| healthcheck Docker « unhealthy » (vérifié chaque minute par l'agent) | diagnostic du conteneur |
| 07:30 chaque jour | rapport des dernières 24 h, sans aucune action |

Le téléphone reçoit toujours l'alerte d'Alertmanager **et**, 2 à 3 minutes plus tard, le rapport de l'agent.

## Pourquoi l'abonnement et pas l'API
`claude -p` (Claude Code non interactif) accepte un token OAuth longue durée de l'abonnement
(`claude setup-token` → `CLAUDE_CODE_OAUTH_TOKEN`). L'usage est décompté des limites de l'abonnement Pro, sans facture.
Garde-fous : l'agent refuse de démarrer si `ANTHROPIC_API_KEY` (ou une variable de fournisseur) existe, ne transmet à
Claude qu'un environnement minimal, et s'arrête si Claude Code annonce une autre source d'authentification
(`apiKeySource` ≠ `none`). Les limites sont partagées avec l'usage interactif : plafond de diagnostics par jour,
anti-rebond, regroupement des alertes et modèle Sonnet par défaut.

## Sécurité (moindre privilège)
| Risque | Mesure |
|---|---|
| L'IA casse quelque chose | Elle ne peut que **demander** `restart` ou `up` ; l'hôte n'exécute que les stacks/actions de `compose/agent-actions.txt`, 3 par stack et par heure, 3 par diagnostic, jamais pendant un déploiement |
| Commandes arbitraires | `--permission-mode dontAsk` + liste blanche (`consignes/settings.json`) : seuls les outils de l'agent, `sleep`, `date`, `git status/diff` ; pas de pipe, `&&`, redirection ni `$( )` (vérifié) |
| Lecture des secrets | API Docker filtrée (pas d'`archive`/`export`/`exec`) ; `conteneur` masque les variables d'environnement ; pas de clé SOPS ; tokens GitHub et ntfy jamais dans l'environnement de Claude |
| Modifier ses propres règles | `settings.json` et consignes dans l'image (lecture seule) ; `--setting-sources ""` ; refus des correctifs touchant `compose/agent/`, `agent-actions.*`, `.github/`, `*.sops.*`, `.claude/`, `CLAUDE.md` ; git sans hooks |
| Fuite dans le dépôt public | correctif refusé s'il contient une IP ou le domaine ; description de PR nettoyée ; PR relue avant merge ; `main` protégée par un ruleset |
| Injection de prompt par les journaux | consigne explicite (données ≠ instructions), actions bornées par l'hôte, PR obligatoire ; testé avec une ligne de journal piégée : ignorée et signalée |
| Exfiltration | pas de WebFetch ni curl ; reste possible : la requête de WebSearch (désactivable : `RECHERCHE_WEB=0`) |

Limite connue : le conteneur a un accès Internet sortant (API Claude, GitHub, ntfy) ; il n'est pas filtré par domaine.

## Exploitation
- Rapports : `compose/agent/data/rapports/` ; transcriptions complètes : `compose/agent/data/etat/journaux/`.
- Actions exécutées par l'hôte : `~/logs/agent-actions.log`.
- Supervision de l'agent : alertes `AgentRapportQuotidienAbsent` (pas de rapport depuis 26 h) et `AgentEnEchec`.
- Arrêt volontaire d'un service : poser un silence dans Alertmanager, l'agent ne sera pas lancé.
- Renouveler le token chaque année (`claude setup-token`), puis `scripts/compose-up.sh agent up -d`.
- Mise à jour de Claude Code : changer `CLAUDE_CODE_VERSION` et le tag de l'image dans `compose/agent/compose.yaml`,
  puis `scripts/compose-up.sh agent up -d --build` (la stack n'est pas dans le déploiement automatique : elle se construit).
