# 04 — Services

État relevé sur le Mini PC le 2026-11-12 (`docker ps`).

## Mini PC HP (Debian + Docker)
| Service | Notes |
|---|---|
| **Traefik** (+ socket-proxy) | Reverse proxy du Mini PC, certificat wildcard Let's Encrypt (DNS-01). Interfaces d'admin limitées au LAN (`lan-admin@docker`) ([stack](../compose/traefik/)) |
| **cloudflared** | Un seul tunnel `homelab` vers Traefik pour tous les noms publics ([stack](../compose/cloudflared/)) |
| **Jellyfin** (stack Docker) | Jellyfin + Seerr, Radarr, Sonarr, Jackett, Transmission derrière gluetun (ProtonVPN). Médias sur un QNAP presque plein. Thème CSS personnalisé ; objectif : arrière-plans activés par défaut pour tous les utilisateurs ([stack](../compose/jellyfin/)) |
| **Vaultwarden** | Gestionnaire de mots de passe, migré depuis le CT du T130, derrière Traefik (`/admin` en LAN seulement) ([stack](../compose/vaultwarden/)) |
| **Immich** | Photos et vidéos (sauvegarde des téléphones), v3.3.5 en service ([stack](../compose/immich/)). **Pas encore sauvegardé ni supervisé** (voir [05](05-stockage-sauvegardes.md)) |
| **Serveur web** | Site vitrine personnel |
| **Arcane** | Interface de gestion Docker, en cours d'adoption ; encore des problèmes, donc beaucoup de CLI ([stack](../compose/arcane/)) |
| **Backrest** | Sauvegardes restic des stacks, chaque nuit vers le Synology, interface web ([stack](../compose/backrest/)) |
| **ConvertX** | Conversion de fichiers ([stack](../compose/convertx/)) |
| **DiscoPanel** | Panel des serveurs Minecraft ([stack](../compose/discopanel/)) |
| **Supervision** | Prometheus, Grafana, Loki, Alertmanager ([stack](../compose/monitoring/)) |
| **ntfy** | Notifications push des alertes et des scripts ([stack](../compose/ntfy/)) |
| **webhook** | Reçoit le push GitHub pour le déploiement automatique ([stack](../compose/webhook/), [doc](14-deploiement-auto.md)) |
| **Agent de dépannage** | Claude Code (abonnement Pro) : diagnostique les pannes signalées par Alertmanager, relance ce qui est autorisé, propose les correctifs en PR, rapport quotidien ([stack](../compose/agent/), [doc](15-agent-depannage.md)) |

## Dell T130 (Proxmox, LXC)
| Service | Notes |
|---|---|
| **npmplus** | Ancien reverse proxy, en cours de retrait : plus aucun service du Mini PC ne passe par lui. À arrêter quand plus aucun hôte n'y est déclaré |
| **Vaultwarden** (CT) | Ancienne instance, remplacée par la stack du Mini PC. À arrêter puis supprimer (état à confirmer) |

## Retirés / abandonnés
Nginx Proxy Manager puis npmplus (remplacés par Traefik), Pi-hole (test), Dockge (remplacé par Arcane / CLI), Jellyfin en LXC,
Portabase (remplacé par Backrest), Watchtower (remplacé par Renovate), GLPI, SoulSync + slskd (retiré le 2026-11-12), 2× serveur CS2 de test (conteneurs supprimés, volume `cs_cs2-data` restant).

## Supervision
Stack [`compose/monitoring`](../compose/monitoring/) sur le Mini PC (octobre 2026), derrière Traefik :
Prometheus + Alertmanager (métriques et alertes), Loki + Alloy (journaux des conteneurs), Grafana (tableaux de bord),
node_exporter (Mini PC, et paquet pfSense), cAdvisor (conteneurs), snmp_exporter en SNMPv3 (NAS, switch),
blackbox (sondes HTTPS et certificats). Les alertes partent sur le téléphone via [`compose/ntfy`](../compose/ntfy/).
Passage prévu à `kube-prometheus-stack` sur K3s (partie 2 de la feuille de route).
