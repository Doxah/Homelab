# 05 — Stockage & sauvegardes

## NAS en service
| NAS | Capacité | Usage |
|---|---|---|
| Synology DS216J | — | Données perso, sauvegardes (Vaultwarden). Accueillait Immich auparavant |
| QNAP TS-259 Pro+ | 4 To RAID1 | Médias Jellyfin, presque plein |
| QNAP TS-228 | 4 To RAID1 | Extension prévue pour Jellyfin |

QNAP TS-231P2 : non utilisé.

## Sauvegardes en place
- **Vaultwarden** → Synology via **rsync daemon**, automatisé. Options : `--no-perms --no-owner --no-group` (sinon erreurs `chgrp` côté Synology).
- Procédure **MySQL PITR** documentée (binlogs + dump nocturne).

## Lacunes
- Aucune sauvegarde Proxmox (vzdump/PBS) des CT du T130.
- Pas de sauvegarde des configs Docker et volumes du Mini PC.
- RAID1 n'est pas une sauvegarde : pas de copie des médias Jellyfin.
