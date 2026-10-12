# 04 — Services

## Mini PC HP (Debian + Docker)
| Service | Notes |
|---|---|
| **Jellyfin** (stack Docker) | Médias sur un QNAP presque plein. Thème CSS personnalisé ; objectif : arrière-plans activés par défaut pour tous les utilisateurs |
| **Serveur web** | Site vitrine personnel |
| **cloudflared ×2** | Un tunnel pour Jellyfin, un pour le site web |
| **Arcane** | Interface de gestion Docker, en cours d'adoption ; encore des problèmes, donc beaucoup de CLI (`docker compose`) |
| **Portabase** | En test |
| **ConvertX** | Conversion de fichiers |
| **GLPI** | Gestion de parc / helpdesk, en test ([stack](../compose/glpi/)) |
| **DiscoPanel** | Panel des serveurs Minecraft |
| **2× serveur CS2** | Tests, à supprimer (trop d'espace disque) |
| **Immich** | À réinstaller |

## Dell T130 (Proxmox, LXC)
| Service | Notes |
|---|---|
| **Vaultwarden** | Sauvegarde rsync vers le Synology |
| **npmplus** | Reverse proxy principal |

## Retirés / abandonnés
Nginx Proxy Manager (remplacé par npmplus), Pi-hole (test), Dockge (remplacé par Arcane / CLI), Jellyfin en LXC.

## Pas de supervision
Le homelab n'a pas encore de monitoring : prévu avec Prometheus, Grafana et Loki sur le futur cluster.
