# Portabase (Mini PC) — sauvegardes du homelab

[Portabase](https://portabase.io) remplace Backrest : un **dashboard** (cette stack) planifie les sauvegardes, gère la rétention,
les destinations et les notifications ; un **agent** ([`portabase-agent`](../portabase-agent/)) fait les sauvegardes et les
envoie directement à la destination.

| | |
|---|---|
| Accès | `https://portabase.<DOMAIN>` via Traefik, postes d'admin uniquement (`lan-admin@docker`) ; `/api/agent/` ouvert à l'agent (authentifié par sa clé), jamais dans le tunnel |
| Données | `./portabase-data`, `./postgres-data` (70:70) — jamais dans Git |
| Secrets | `secrets.sops.env` : `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `PROJECT_SECRET` ; `DOMAIN` dans `compose/commun.sops.env` |
| Versions | `portabase/portabase:1.36.2`, `portabase/agent:1.26.3` (figées, Renovate) |

Les fichiers `secrets.sops.env` sont ceux de l'ancienne instance (retirée le 2026-10-25) : ils correspondent aux dossiers
`portabase-data` et `postgres-data` restés sur le Mini PC. Pour repartir de zéro : supprimer ces deux dossiers (sudoer, 70:70),
régénérer les secrets (`openssl rand -hex 32`), puis recréer le compte admin et l'agent.

## Ce qui change par rapport à Backrest
| | Backrest | Portabase |
|---|---|---|
| Moteur des fichiers | restic | restic aussi (mode *Snapshots* de l'agent) : dédoublonnage, chiffrement, un dépôt par source |
| Bases SQLite | conteneurs arrêtés la nuit (hooks) | `sqlite3 .backup` à chaud, copie cohérente : **plus aucun arrêt de service** |
| Accès Docker | socket-proxy limité à stop/start | **aucun** (pas de socket) |
| Mot de passe des dépôts | `RESTIC_PASSWORD` (SOPS + Vaultwarden + papier) | dérivé de la clé maîtresse contenue dans `EDGE_KEY` (voir « Clé critique ») |
| Alertes | métriques `.prom` → `SauvegardeEnRetard` (> 26 h) + ntfy en cas d'échec | ntfy depuis le dashboard en cas d'échec ; **pas de métriques Prometheus** (voir « Limites ») |
| Nouveau | — | PostgreSQL, Home Assistant, sources ajoutées depuis l'interface |

## Clé critique : `EDGE_KEY`
Le mot de passe restic de chaque source est dérivé (HKDF-SHA256) de la clé maîtresse contenue dans `EDGE_KEY`
et du `generated_id` de la source dans [`databases.json`](../portabase-agent/databases.json).
**Sans `EDGE_KEY`, aucune sauvegarde n'est lisible**, même avec restic seul. Donc :
- garder une copie de `EDGE_KEY` dans Vaultwarden **et** sur papier, comme l'ancien mot de passe restic ;
- ne jamais changer un `generated_id` existant (nouveau mot de passe = nouveau dépôt) ;
- régénérer la clé de l'agent dans le dashboard = nouvelles sauvegardes illisibles avec l'ancienne : refaire une sauvegarde complète.

## Mise en service
Backrest **reste en place** jusqu'à un test de restauration réussi depuis Portabase (comme pour l'ancien script Vaultwarden).

### 1. Prérequis
- pfSense : remettre le host override `portabase.<domaine>` → Mini PC (supprimé lors du retrait d'octobre).
- Synology : dossier partagé dédié (ex. `portabase`) et compte `backup_portabase` en SFTP, clé SSH dédiée
  (même procédure et mêmes pièges que `backup_minipc`, voir [Backrest](../backrest/README.md#dépannage)).

### 2. Lancer
```bash
scripts/compose-up.sh portabase
scripts/compose-up.sh portabase-agent
docker logs -f portabase-agent       # « 18 instances loaded », agent « en ligne » dans le dashboard
```

### 3. Configurer le dashboard
1. **Storage** : canal `synology` en SFTP (hôte, port, utilisateur, clé privée, empreinte de la clé d'hôte), dossier `portabase`.
   Le stockage `local` est à éviter : il garderait les sauvegardes sur le Mini PC.
2. **Notifications** : canal ntfy, serveur `https://ntfy.<domaine>`, topic `homelab-sauvegardes`, token du compte `scripts`.
3. **Sources** (créées par l'agent depuis `databases.json`) : rattacher chaque source au stockage `synology` et à ntfy,
   activer le chiffrement, puis régler planning et rétention :

| Source(s) | Heure | Rétention (GFS) |
|---|---|---|
| `vaultwarden-base`, `vaultwarden-fichiers` | 05:00 | 30 j, 8 sem, 12 mois |
| `hote` | 05:05 | 7 j, 4 sem, 6 mois |
| `traefik`, `grafana-base`, `grafana-fichiers` | 05:10 | 7 j, 4 sem, 6 mois |
| `arcane-base`, `arcane-fichiers` | 05:15 | 7 j, 4 sem, 6 mois |
| `discopanel-base`, `discopanel-fichiers` | 05:30 | 7 j, 4 sem, 6 mois |
| `jellyfin-base`, `radarr-base`, `sonarr-base`, `seerr-base`, `jellyfin-config` | 05:45 | 7 j, 4 sem, 6 mois |
| `immich-dumps` | 05:50 | 7 j, 4 sem, 6 mois |
| `homeassistant-base`, `homeassistant-fichiers` | 05:55 | 7 j, 4 sem, 6 mois |

L'agent traite une sauvegarde à la fois (`MAX_CONCURRENT_BACKUPS=1`) : les sources d'un même créneau passent à la suite.

### 4. Vérifier
- Lancer une sauvegarde manuelle de chaque source : statut *success*, taille cohérente avec `du -sh`.
- **Bases SQLite** : les sources sont montées en `:ro`. Si une base en mode WAL échoue (`attempt to write a readonly database`
  ou `unable to open database`), passer **ce seul montage** en lecture-écriture dans `portabase-agent/compose.yaml` et le noter ici.
- **Restauration** : restaurer `vaultwarden-base` et `vaultwarden-fichiers` vers `/restauration` (= `portabase-agent/restauration`),
  puis `sqlite3 restauration/.../db.sqlite3 'PRAGMA integrity_check'` → `ok`. Supprimer le dossier restauré ensuite.

### 5. Retirer Backrest (après le test, PR séparée)
`scripts/compose-up.sh backrest down`, retirer `compose/backrest`, les fichiers `monitoring/data/textfile/backrest-*.prom`
et l'alerte `SauvegardeEnRetard` (ou la remplacer). Garder l'ancien dépôt restic sur le Synology jusqu'à ce que Portabase
ait la même profondeur d'historique (12 mois pour Vaultwarden), il se lit avec `restic` et `RESTIC_PASSWORD`.

## Limites connues
- **Pas d'alerte « sauvegarde manquée »** dans Prometheus : Portabase notifie un échec, pas une sauvegarde qui ne s'est jamais lancée
  (agent arrêté, dashboard en panne). À combler : sonde blackbox sur `/api/health` du dashboard + alerte si l'agent est arrêté
  (`ConteneurDisparu` couvre déjà `portabase-agent` s'il disparaît).
- **Minecraft** : les mondes sont copiés à chaud (DiscoPanel n'est plus arrêté). Activer les sauvegardes planifiées de DiscoPanel
  (dossier `discopanel/backups`, sauvegardé lui aussi) pour avoir une copie propre des mondes.
- **Immich** : seule la base est sauvegardée (dumps) ; les photos originales attendent le NAS central (inchangé).
- Le dashboard et sa base sont sur le Mini PC : en cas de perte du Mini PC, restaurer avec `restic` directement depuis le Synology
  (mot de passe dérivé de `EDGE_KEY`), pas besoin du dashboard.

## Moindre privilège
- `portabase-app` : **exception documentée**, l'image lance nginx, tusd et next-server en root. Atténuation :
  `cap_drop: ALL` + `CHOWN DAC_OVERRIDE FOWNER SETUID SETGID NET_BIND_SERVICE`, `no-new-privileges`, 1 Go / 1 CPU.
- `portabase-pg` : `user: 70:70`, `cap_drop: ALL`, lecture seule (tmpfs `/tmp` et `/var/run/postgresql`), réseau interne.
- `portabase-agent` : voir [son README](../portabase-agent/README.md).
