# Portabase (Mini PC)

Tableau de bord de sauvegarde des bases de données (en test). Dashboard + PostgreSQL 17 sur un réseau interne.

| | |
|---|---|
| Accès | `https://portabase.<DOMAIN>` via Traefik, postes d'admin uniquement (`lan-admin@docker`) |
| Données | `./portabase-data` (dont sauvegardes locales), `./postgres-data` — jamais dans Git |
| Secrets | `secrets.sops.env` : `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `PROJECT_SECRET` ; `DOMAIN` dans `compose/commun.sops.env` |

`DATABASE_URL` et `PROJECT_URL` sont construits dans `compose.yaml` à partir de ces variables.
L'inscription libre est fermée (`AUTH_SIGNUP_ENABLED=false`).

## Moindre privilège
- `portabase-app` : **exception documentée**, l'image lance nginx, tusd et next-server en root. Atténuation :
  `cap_drop: ALL` + `CHOWN DAC_OVERRIDE FOWNER SETUID SETGID NET_BIND_SERVICE`, `no-new-privileges`, 1 Go / 1 CPU.
- `portabase-pg` : `user: 70:70`, `cap_drop: ALL`, lecture seule (tmpfs `/tmp` et `/var/run/postgresql`), 512 Mo.
  `./postgres-data` doit appartenir à 70:70 (`stat -c %u:%g postgres-data`).

## Migration vers ce dossier (une seule fois)
```bash
cd <ancien dossier> && docker compose down
mv portabase-data postgres-data ~/Homelab/compose/portabase/
cd ~/Homelab && scripts/compose-up.sh portabase config --quiet && scripts/compose-up.sh portabase
```
Supprimer ensuite l'ancien `.env` en clair.
