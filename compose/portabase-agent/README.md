# Agent Portabase (Mini PC)

Sauvegarde les éléments listés dans `databases.json` (aujourd'hui : le volume Docker d'Arcane) et les envoie au
dashboard [Portabase](../portabase/).

| | |
|---|---|
| Dashboard joint | URL contenue dans `EDGE_KEY` (`https://portabase.<DOMAIN>`, via Traefik, router `portabase-agent` sur `/api/agent/`) |
| Secrets | `secrets.sops.env` : `EDGE_KEY` (clé d'appairage générée par le dashboard) |
| Config | `databases.json` (versionné : ne contient ni mot de passe ni IP) |

## Lancer
```bash
scripts/compose-up.sh portabase-agent
docker logs -f portabase-agent      # l'agent doit apparaître « en ligne » dans le dashboard
```
Le nom `portabase.<DOMAIN>` doit résoudre vers le Mini PC (host override pfSense) : l'agent passe par Traefik, comme un navigateur.

## Ajouter une base à sauvegarder
Ajouter l'entrée dans le dashboard ou avec la CLI Portabase, puis reporter `databases.json` dans le dépôt.
Une base avec mot de passe : ne pas le committer en clair (passer par une variable SOPS).

## Notes
- Le fichier de la CLI s'appelait `database.json` alors que le compose montait `databases.json` : Docker aurait créé un
  **dossier** `databases.json` vide (en root). Renommé en `databases.json`.
- `TZ` corrigé en `Europe/Paris` (`UTC+2` est inversé en notation POSIX).
- Exception au moindre privilège : socket Docker (sauvegarde de volumes) et processus en root.
  Atténuation : `cap_drop: ALL` (root suffit pour le socket, qui lui appartient), `no-new-privileges`, 512 Mo / 1 CPU.
