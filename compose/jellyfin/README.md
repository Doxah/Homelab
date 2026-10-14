# Stack Jellyfin (Mini PC)

Jellyfin + Seerr (requêtes) + Radarr / Sonarr / Jackett + Transmission derrière gluetun (ProtonVPN, port forwarding)
+ Watchtower (mises à jour nocturnes, sauf gluetun et transmission). Détails des chemins NAS en tête de `compose.yaml`.

## Secrets (`secrets.sops.env`, chiffré)
`NAS_ROOT`, `NAS_2_ROOT` (montages NAS), `VPN_TYPE`, `OPENVPN_USER` (suffixe `+pmp`), `OPENVPN_PASSWORD`,
`WIREGUARD_PRIVATE_KEY`, `SERVER_COUNTRIES`. `DOMAIN` vient de `compose/commun.sops.env`.

## Accès (Traefik)
| Hôte | Accès | Remarque |
|---|---|---|
| `videos.<DOMAIN>` | LAN | 8096 reste aussi publié (tunnel cloudflared, clients TV en IP) |
| `demande-videos.<DOMAIN>` | LAN | 5055 reste aussi publié (tunnel cloudflared) |
| `radarr.` / `sonarr.` / `jackett.<DOMAIN>` | postes d'admin (`lan-admin@docker`) | plus de port publié |
| `transmission.<DOMAIN>` | postes d'admin | via `compose/traefik/dynamic/transmission.yml` → `BIND_IP:9091` (l'UI vit dans le réseau de gluetun) |

## Migration vers ce dossier (une seule fois)
La stack tournait depuis un autre dossier avec un `.env` en clair. Les noms (`name: jellyfin-stack`, `container_name`) sont
identiques : les conteneurs sont simplement recréés.
```bash
cd <ancien dossier> && docker compose down
mv config ~/Homelab/compose/jellyfin/          # même chemin relatif ./config
cd ~/Homelab && scripts/compose-up.sh jellyfin config --quiet && scripts/compose-up.sh jellyfin
```
Supprimer ensuite l'ancien `.env` en clair.

## À vérifier dans les applis (ports retirés)
Les applis doivent se joindre par **nom de conteneur**, plus par l'IP du Mini PC :
| Appli | Réglage | Valeur |
|---|---|---|
| Radarr / Sonarr | Indexers (Torznab Jackett) | `http://jackett:9117/...` |
| Radarr / Sonarr | Download Clients → Transmission | hôte `gluetun`, port `9091` |
| Seerr | Jellyfin | `http://jellyfin:8096` |
| Seerr | Radarr / Sonarr | `radarr:7878` / `sonarr:8989` |
| Radarr / Sonarr | Connect → Jellyfin | `http://jellyfin:8096` |

## Points ouverts
- Images en `latest` + Watchtower : à remplacer par des versions figées + Renovate (objectif git).
- Watchtower monte le socket Docker en écriture (objectif moindre privilège).
- Transmission sans mot de passe et 9091 publié sur toutes les interfaces : restreindre (pfSense ou `USER`/`PASS`).
