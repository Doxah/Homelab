# 04 — Services

## Mini PC HP (Debian + Docker)
| Service | Notes |
|---|---|
| **Jellyfin** (stack Docker) | Médias sur un QNAP presque plein. Thème CSS personnalisé ; objectif : arrière-plans activés par défaut pour tous les utilisateurs |
| **Serveur web** | Site vitrine personnel |
| **cloudflared ×2** | Un tunnel pour Jellyfin, un pour le site web |
| **Arcane** | Interface de gestion Docker, en cours d'adoption ; encore des problèmes, donc beaucoup de CLI (`docker compose`) |
| **Backrest** | Sauvegardes restic de toutes les stacks, chaque nuit vers le Synology, interface web ([stack](../compose/backrest/)) |
| **ConvertX** | Conversion de fichiers |
| **GLPI** | Gestion de parc / helpdesk, en test ([stack](../compose/glpi/)) |
| **SoulSync + slskd** | Stack musique « Spotify selfhost » : découverte, téléchargement Soulseek, rangement vers la bibliothèque Jellyfin, en préparation ([stack](../compose/soulsync/)) |
| **DiscoPanel** | Panel des serveurs Minecraft |
| **Supervision** | Prometheus, Grafana, Loki, Alertmanager ([stack](../compose/monitoring/)) |
| **ntfy** | Notifications push des alertes et des scripts ([stack](../compose/ntfy/)) |
| **2× serveur CS2** | Tests, à supprimer (trop d'espace disque) |
| **Immich** | À réinstaller |

## Dell T130 (Proxmox, LXC)
| Service | Notes |
|---|---|
| **Vaultwarden** | Sauvegarde rsync vers le Synology |
| **npmplus** | Reverse proxy principal |

## Retirés / abandonnés
Nginx Proxy Manager (remplacé par npmplus), Pi-hole (test), Dockge (remplacé par Arcane / CLI), Jellyfin en LXC.

## Supervision
Stack [`compose/monitoring`](../compose/monitoring/) sur le Mini PC (octobre 2026), derrière Traefik :
Prometheus + Alertmanager (métriques et alertes), Loki + Alloy (journaux des conteneurs), Grafana (tableaux de bord),
node_exporter (Mini PC, et paquet pfSense), cAdvisor (conteneurs), snmp_exporter en SNMPv3 (NAS, switch),
blackbox (sondes HTTPS et certificats). Les alertes partent sur le téléphone via [`compose/ntfy`](../compose/ntfy/).
Passage prévu à `kube-prometheus-stack` sur K3s (partie 2 de la feuille de route).
