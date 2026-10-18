# Stack Jellyfin (Mini PC)

Jellyfin + Seerr (requêtes) + Radarr / Sonarr / Jackett + Transmission derrière gluetun (ProtonVPN, port forwarding)
(VPN, port forwarding). Détails des chemins NAS en tête de `compose.yaml`.
Mises à jour : versions figées, proposées par Renovate (Watchtower retiré le 2026-10-18).

## Moindre privilège
| Conteneur | Réglages | Exception |
|---|---|---|
| jellyfin, radarr, sonarr, jackett, transmission | `cap_drop: ALL` + `CHOWN DAC_OVERRIDE FOWNER SETUID SETGID KILL`, `no-new-privileges`, limites | s6 (init linuxserver) démarre en root puis lance l'appli en PUID 1000 ; pas de `read_only` |
| seerr | non-root (node), `cap_drop: ALL`, `no-new-privileges`, limites | pas de `read_only` (cache Next.js) |
| gluetun | `NET_ADMIN`, `no-new-privileges`, limites | root + `NET_ADMIN` + `/dev/net/tun` indispensables au tunnel |
| jellyfin | `/dev/dri` + groupe `render` | transcodage matériel QuickSync |

Vérifier après un changement : `docker top <conteneur> -o pid,user,comm` (l'appli doit tourner en 1000) et `docker logs <conteneur>`.
Si un conteneur linuxserver ne démarre plus (`Operation not permitted`), rajouter la capacité citée dans `&lsio-caps`.

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
- Watchtower supprimé (il montait le socket Docker en écriture) : après le déploiement, `docker rm -f watchtower`
  ou `scripts/compose-up.sh jellyfin up -d --remove-orphans`.
- gluetun : tester `cap_drop: ALL` avec le minimum de capacités (voir le commentaire dans `compose.yaml`).
- Transmission sans mot de passe et 9091 publié sur toutes les interfaces : restreindre (pfSense ou `USER`/`PASS`).
