# 05 — Stockage & sauvegardes

## NAS en service
| NAS | Capacité | Usage |
|---|---|---|
| Synology DS216J | ~500 Go libres (oct. 2026) | Données perso, sauvegardes (Vaultwarden, dépôt restic du Mini PC). Accueillait Immich auparavant |
| QNAP TS-259 Pro+ | 4 To RAID1 | Médias Jellyfin, presque plein |
| QNAP TS-228 | 4 To RAID1 | Extension prévue pour Jellyfin |

QNAP TS-231P2 : non utilisé (candidat pour le NAS externalisé).

## Sauvegardes en place
- **Mini PC → [Backrest](../compose/backrest/)** (restic, depuis 2026-10) : un plan par stack chaque nuit entre 5h et 6h, dépôt chiffré
  sur le Synology en SFTP, conteneurs arrêtés le temps de leur sauvegarde (bases SQLite cohérentes), alerte si un plan n'a pas réussi
  depuis 26 h, notification ntfy en cas d'échec. Détail des plans, exclusions et restauration : [README de la stack](../compose/backrest/README.md).
- **Vaultwarden** : l'ancien script `scripts/vaultwarden-backup.sh` (cron 3h15, archive + rsync vers le Synology) a été retiré
  le 2026-10-26 après un test de restauration réussi depuis Backrest.
- Procédure **MySQL PITR** documentée (binlogs + dump nocturne).

## Inventaire (octobre 2026)
| Donnée | Où | Criticité | Couverture |
|---|---|---|---|
| Clé age du PC (SOPS) | PC | Critique : sans elle, aucun secret du dépôt n'est lisible | Copie hors homelab (feuille de route git.8) |
| Mot de passe du dépôt restic | SOPS (`compose/backrest`) | Critique | + Vaultwarden + papier |
| Vaultwarden | `compose/vaultwarden/data` | Critique | Backrest `vaultwarden` (30 j / 8 sem / 12 mois) + script rsync |
| Dossier `private/` du dépôt | PC | Critique (hors Git) | À couvrir avec la sauvegarde du PC |
| Config pfSense (`config.xml`) | pfSense | Critique | **À faire** |
| Hôte Mini PC (`/etc`, crontabs, `~/.ssh`, clé age du Mini PC) | Mini PC | Important | Backrest `hote` |
| Config Jellyfin + *arr, Seerr, Jackett, Transmission | `compose/jellyfin/config` | Important | Backrest `jellyfin` (sans caches, métadonnées, logs) |
| Serveurs Minecraft + base DiscoPanel | données DiscoPanel | Important | Backrest `discopanel` |
| SoulSync + slskd | `compose/soulsync` | Important | Backrest `soulsync` |
| Arcane | volume `arcane_arcane-data` | Moyen | Backrest `arcane` (remplace Portabase) |
| `acme.json` Traefik, Grafana | `compose/traefik/data`, `compose/monitoring/data/grafana` | Faible | Backrest `infra` |
| Médias famille, musique, données perso des NAS | NAS | À qualifier | **Pas encore** : avec le NAS central |
| Médias Jellyfin | QNAP | Faible (re-téléchargeables) | Non |
| Prometheus, Loki, ntfy, ConvertX | Mini PC | Aucune / déclaratif | Non |

## Lacunes
- Aucune copie hors site : tout est à la maison (incendie, vol, ransomware). Prévu : NAS externalisé, réplication non effaçable.
- Synology presque seul support des sauvegardes, ~500 Go libres : choisir le NAS central (feuille de route, backup.2).
- Config pfSense et PC non sauvegardés.
- Aucune sauvegarde Proxmox (vzdump/PBS) des CT du T130 (voués à disparaître).
- RAID1 n'est pas une sauvegarde : pas de copie des médias Jellyfin.
