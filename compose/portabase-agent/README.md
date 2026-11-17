# Agent Portabase (Mini PC)

Sauvegarde les sources de [`databases.json`](databases.json) et les envoie à la destination réglée dans le
[dashboard Portabase](../portabase/) (Synology en SFTP). Mise en service, planning et rétention : [README du dashboard](../portabase/README.md).

| | |
|---|---|
| Dashboard joint | URL contenue dans `EDGE_KEY` (`https://portabase.<DOMAIN>`, router `portabase-agent` sur `/api/agent/`) |
| Secrets | `secrets.sops.env` : `EDGE_KEY` (clé d'appairage générée par le dashboard). **Critique** : voir « Clé critique » dans le README du dashboard |
| Config | `databases.json` (versionné : ni mot de passe ni IP) |
| Données | `./data` (cache restic, temporaires), `./restauration` (cible des restaurations) — jamais dans Git |

## Sources
Deux types seulement, sans mot de passe :
- `sqlite` : copie à chaud cohérente par `sqlite3 .backup` (une source par base) ;
- `files` en mode `snapshot` (restic) : le reste du dossier, **en excluant les bases** déjà copiées par `sqlite`
  (une copie de fichier d'une base ouverte peut être inutilisable).

Les `generated_id` ne doivent **jamais changer** : ils servent à dériver le mot de passe du dépôt restic de chaque source.
Pour une nouvelle source : nouvel UUID (`python3 -c 'import uuid; print(uuid.uuid4())'`), monter le dossier en `:ro`
dans `compose.yaml`, puis `scripts/compose-up.sh portabase-agent`.

Une base **avec mot de passe** (PostgreSQL, MySQL…) : `databases.json` ne lit pas les variables d'environnement, donc ne
pas l'y mettre (dépôt public). La déclarer dans le dashboard (stockée dans sa base) ou passer par un dump, comme Immich.

## Moindre privilège
- **Pas de socket Docker** : seul le type `docker-volume` en a besoin (il arrête le conteneur et crée un conteneur
  d'aide). Le volume d'Arcane est monté directement en `:ro`. Ne pas ajouter de source `docker-volume` sans en reparler.
- **Exception documentée** : root + `DAC_READ_SEARCH` (lire les données de tous les UID), `DAC_OVERRIDE`, `CHOWN`,
  `FOWNER` (restaurer propriétaires et droits dans `./restauration`), `no-new-privileges`, 1 Go / 1 CPU.
- Sources en `:ro` : une restauration va toujours dans `./restauration`, puis se recopie à la main, service arrêté.

## Dépannage
| Symptôme | Cause probable |
|---|---|
| Agent « hors ligne » dans le dashboard | `portabase.<domaine>` ne résout pas vers le Mini PC (host override pfSense) ; `docker logs portabase-agent` |
| `Config file not found` | `databases.json` absent : Docker a créé un **dossier** à la place, le supprimer (root) puis relancer |
| `readonly database` sur une source `sqlite` | Base en WAL sur un montage `:ro` : voir « Vérifier » dans le README du dashboard |
| `restic …: wrong repository password` | `EDGE_KEY` régénérée ou `generated_id` modifié |
| `permission denied` sur une source | Capacité `DAC_READ_SEARCH` absente ou montage manquant |
