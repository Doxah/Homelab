# Backrest (Mini PC)

Sauvegarde versionnée et chiffrée des données du Mini PC avec [restic](https://restic.net/), pilotée par
[Backrest](https://github.com/garethgeorge/backrest) : planification, rétention, prune et check dans une interface web,
navigation dans les snapshots et restauration fichier par fichier. Remplace Portabase (qui ne sauvegardait que le volume d'Arcane)
et, après un test de restauration, le script `scripts/vaultwarden-backup.sh`.

```
                      05:00-05:45, un plan après l'autre
backrest ──► hook « avant » ──► socket-proxy-backrest ──► docker stop <conteneurs du plan>
   │
   ├──► restic backup /sources/<plan> (lecture seule) ──► SFTP ──► Synology : /<partage>/minipc (dépôt chiffré)
   │
   ├──► hook « apres »  ──► docker start (seulement ceux que « avant » a arrêtés)
   ├──► hook « succes » ──► monitoring/data/textfile/backrest-<plan>.prom ──► Prometheus (SauvegardeEnRetard > 26 h)
   └──► hook « erreur » ──► ntfy (topic homelab-sauvegardes)
```

## Choix
| Sujet | Choix | Pourquoi |
|---|---|---|
| Outil | Backrest 1.14.1 (restic 0.19.1) | Interface pour voir l'état des sauvegardes et restaurer ; restic dessous (dédoublonnage, chiffrement, dépôt lisible sans Backrest) |
| Destination | Synology DS216J en SFTP, compte de service dédié | Déjà la cible de Vaultwarden. ~500 Go libres : suffisant pour ces données, à revoir avec le NAS central (feuille de route, backup.2) |
| Secrets | URI et mot de passe du dépôt dans SOPS, passés en `${VAR}` dans `config.json` | Rien de sensible en clair dans la config de Backrest |
| Cohérence des bases | Arrêt des conteneurs du plan pendant sa sauvegarde, la nuit | SQLite (Vaultwarden, *arr, Jellyfin, SoulSync, Arcane, DiscoPanel, Grafana) : une copie à chaud peut être inutilisable |
| Accès Docker | `socket-proxy-backrest` : `POST /containers/<nom>/(stop\|start)` pour une liste fermée de noms | Ni lecture, ni création, ni exec : Backrest ne peut rien faire d'autre qu'arrêter/relancer ces conteneurs |
| Moindre privilège | root + `DAC_OVERRIDE`, `CHOWN`, `FOWNER` ; sources en `:ro` | Lire les données de tous les UID et restaurer propriétaires et dates. Exception détaillée en tête de `compose.yaml` |
| Supervision | Fichier `.prom` par plan + notification ntfy | Même mécanisme que le script Vaultwarden : l'alerte existante `SauvegardeEnRetard` couvre tous les plans |

## Ce qui est sauvegardé
Un plan par stack, tous dans le dépôt restic `minipc` (tag `plan:<nom>`). Horaires en heure de Paris ; Backrest exécute
les tâches **une par une**, les horaires donnent seulement l'ordre.

| Plan | Heure | Contenu (monté en `:ro` sous `/sources/…`) | Conteneurs arrêtés | Rétention |
|---|---|---|---|---|
| `vaultwarden` | 05:00 | `vaultwarden/data` (base, `rsa_key.pem`, pièces jointes) | vaultwarden | 30 j, 8 sem, 12 mois |
| `hote` | 05:05 | `/etc` (ufw, fstab, ssh, cron…), crontabs, `~/.ssh`, `~/.config/sops` (clé age du Mini PC) | aucun | 7 j, 4 sem, 6 mois |
| `infra` | 05:10 | `traefik/data` (`acme.json`), `monitoring/data/grafana`, config de Backrest | grafana | 7 j, 4 sem, 6 mois |
| `arcane` | 05:15 | volume `arcane_arcane-data` | arcane | 7 j, 4 sem, 6 mois |
| `soulsync` | 05:20 | `soulsync/config`, `data`, `slskd` (sans logs ni téléchargements) | soulsync, slskd | 7 j, 4 sem, 6 mois |
| `discopanel` | 05:30 | données DiscoPanel (base + serveurs Minecraft, sans `logs`/`crash-reports`) | discopanel → arrête lui-même les serveurs Minecraft | 7 j, 4 sem, 6 mois |
| `jellyfin` | 05:45 | `jellyfin/config` : Jellyfin, Radarr, Sonarr, Jackett, Seerr, Transmission | seerr, radarr, sonarr, jackett, transmission, jellyfin (pas gluetun) | 7 j, 4 sem, 6 mois |

Exclus du plan `jellyfin` (re-téléchargeable ou sans valeur) : `cache/`, `log/`, `data/metadata/` (images et métadonnées :
Jellyfin les retélécharge, au prix d'un rescan), `transcodes/`, `MediaCover/`, `logs/`, `logs.db`, `Backups/` des *arr, `gluetun/`.

Volontairement **non sauvegardé** : médias et musique des NAS (plus tard, avec le NAS central), Prometheus/Loki/Alloy
(volumineux, reconstructible), ntfy (comptes déclaratifs dans Git), ConvertX, webhook, cloudflared (tout est dans SOPS), GLPI (arrêté).
Le code et les secrets chiffrés sont sur GitHub.

Maintenance du dépôt : `prune` le dimanche à 06:30 (si plus de 10 % d'espace inutilisé), `check` le 1er du mois à 07:00
(relit 5 % des données pour détecter une corruption sur le NAS).

## Arrêt et relance des conteneurs
Hooks du dépôt dans `config.json` → [`hooks/backrest-hook.sh`](hooks/backrest-hook.sh) :

| Événement | Action | Si ça échoue |
|---|---|---|
| Début du snapshot | `avant <plan>` : `docker stop` des conteneurs du plan qui tournent, noms notés dans `data/backrest/etat-hooks/<plan>.arretes` | Relance immédiate de ceux déjà arrêtés, sauvegarde annulée, notification |
| Fin du snapshot (succès ou échec) | `apres <plan>` : `docker start` des conteneurs notés, dans l'ordre inverse | Notification priorité max (« relance en échec ») ; le fichier d'état est gardé |
| Snapshot réussi | `succes <plan>` : écrit `backrest-<plan>.prom` | — |
| Erreur (backup, prune, check…) ou sauvegarde partielle | `erreur` : notification ntfy avec le détail | — |

Un conteneur **déjà arrêté** avant la sauvegarde n'est pas relancé ; un conteneur absent (stack non déployée) est ignoré.

**Pas besoin de SOPS pour relancer** : `docker start` redémarre le conteneur existant, avec l'environnement (secrets compris)
injecté à sa création par `scripts/compose-up.sh`. Rien n'est recréé. Seul un `up`/recréation demande les secrets.

## Secrets (`secrets.sops.env`, chiffré)
Livré **pré-rempli** avec une ligne commentée par variable : `sops compose/backrest/secrets.sops.env`, décommenter, remplacer.

| Variable | Rôle |
|---|---|
| `RESTIC_REPO_MINIPC` | URI du dépôt : `sftp://backup_minipc@<ip-du-nas>:<port-ssh>//<partage>/minipc` (chemin tel que vu en SFTP, voir plus bas) |
| `RESTIC_PASSWORD_MINIPC` | `openssl rand -hex 32`. **Aussi dans Vaultwarden et sur papier** : sans lui, les sauvegardes sont illisibles |
| `NTFY_TOKEN` | Token du compte ntfy `scripts` (même valeur que `NTFY_TOKEN` de `compose/webhook/secrets.sops.env`) |
| `DISCOPANEL_HOST_DATA_PATH` | Même valeur que dans `compose/discopanel/secrets.sops.env` |
| `DOCKER_GID` | `getent group docker \| cut -d: -f3` |

Pourquoi le mot de passe doit exister hors du homelab : Vaultwarden est lui-même dans ce dépôt restic. En cas de perte du Mini PC,
le chemin de secours est **clé age du PC** (sauvegardée hors homelab) → `sops -d compose/backrest/secrets.sops.env` depuis GitHub.
Le papier couvre le cas où le PC est perdu aussi.

## Mise en service

### 1. Synology : compte de service et SFTP
DSM 7.2, avec un compte administrateur :
1. **Dossier partagé** pour les sauvegardes (ou celui de Vaultwarden), et dedans un dossier `minipc`.
2. **Utilisateur** `backup_minipc` : pas administrateur, lecture/écriture sur ce dossier partagé **uniquement** (aucun accès ailleurs),
   *Privilèges des applications* : **SFTP** seulement.
3. **Services de fichiers → FTP → SFTP** : activer. Le port est celui du service SSH.
4. Service d'accueil des utilisateurs déjà activé (fait pour Vaultwarden) : nécessaire pour `authorized_keys`.

### 2. Mini PC : dossiers, clé SSH, configuration
```bash
cd ~/Homelab/compose/backrest
mkdir -p data/config data/backrest data/cache data/ssh data/restauration     # AVANT le 1er lancement (sinon : échec explicite)
cp config.modele.json data/config/config.json                               # une seule fois : ensuite, l'interface fait foi

ssh-keygen -t ed25519 -f data/ssh/id_ed25519 -N "" -C "backrest@minipc"      # sans phrase de passe : utilisée la nuit
ssh-keyscan -p <port-ssh> <ip-du-nas> > data/ssh/known_hosts                # vérifier l'empreinte affichée dans DSM si besoin
cat data/ssh/id_ed25519.pub
```
Sur le NAS, en SSH avec un compte administrateur puis `sudo -i` (même méthode que pour Vaultwarden) :
```bash
H=/var/services/homes/backup_minipc
mkdir -p $H/.ssh
echo 'from="<ip-du-mini-pc>",no-pty,no-port-forwarding,no-agent-forwarding,no-X11-forwarding <contenu de id_ed25519.pub>' >> $H/.ssh/authorized_keys
chown -R backup_minipc:users $H/.ssh
chmod 755 $H && chmod 700 $H/.ssh && chmod 600 $H/.ssh/authorized_keys
```
Test depuis le Mini PC, et **repérer le chemin du dépôt tel que SFTP le voit** :
```bash
sftp -i data/ssh/id_ed25519 -o UserKnownHostsFile=data/ssh/known_hosts -o IdentitiesOnly=yes -P <port-ssh> backup_minipc@<ip-du-nas>
sftp> pwd        # en général « / » : les dossiers partagés apparaissent à la racine
sftp> ls         # → <partage>
sftp> ls <partage>/minipc
```
Si `ls` montre le dossier partagé à la racine, l'URI est `sftp://backup_minipc@<ip-du-nas>:<port-ssh>//<partage>/minipc`
(le `//` après le port = chemin absolu). Un `/volume1/…` ne fonctionne pas en SFTP sur DSM.

Puis remplir les secrets : `sops compose/backrest/secrets.sops.env` (depuis le PC Windows, puis commit/push).

### 3. Estimer la place
```bash
cd ~/Homelab/compose
du -sh vaultwarden/data traefik/data monitoring/data/grafana soulsync/{config,data,slskd} 2>/dev/null
du -sh --exclude=metadata --exclude=cache --exclude=MediaCover --exclude=log --exclude=logs jellyfin/config 2>/dev/null
sops exec-env discopanel/secrets.sops.env 'du -sh "$DISCOPANEL_HOST_DATA_PATH"'
docker system df -v | grep arcane_arcane-data
```
Les dossiers en root ou en 70:70 peuvent être illisibles sans sudo : ordre de grandeur seulement. restic compresse et dédoublonne ;
le premier snapshot pèse à peu près la taille des sources, les suivants seulement les changements.

### 4. DiscoPanel : démarrage automatique des serveurs
En s'arrêtant, DiscoPanel arrête proprement les serveurs Minecraft qu'il gère (monde enregistré) ; au redémarrage il relance
**uniquement ceux qui ont « Auto start » activé**. Vérifier ce réglage sur chaque serveur qui doit tourner, sinon il restera arrêté
après 5h30. Un serveur « Detached » n'est pas arrêté : sa copie peut alors être incohérente.

### 5. DNS
pfSense → *Services → DNS Resolver → Host Overrides* : `backrest.<domaine>` → IP du Mini PC (comme les autres services Traefik).

### 6. Lancement
```bash
cd ~/Homelab
scripts/compose-up.sh backrest config --quiet && scripts/compose-up.sh backrest pull && scripts/compose-up.sh backrest
docker ps --filter name=backrest                  # backrest et socket-proxy-backrest (healthy)
docker logs backrest | grep -iE 'error|initializ' # « auto-initializing repo » au 1er lancement : dépôt créé sur le NAS
```
Une fois en service, ajouter `backrest` à [`compose/deploiement-auto.txt`](../deploiement-auto.txt) pour qu'un push le redéploie
(pas avant : tant que `data/` et les secrets n'existent pas sur le Mini PC, le déploiement automatique échouerait).

### 7. Premier accès et première sauvegarde
1. `https://backrest.<domaine>` : la fenêtre de réglages s'ouvre, **créer le compte** tout de suite (l'interface n'a pas
   d'authentification tant qu'aucun compte n'existe). Laisser l'*Instance ID* à `minipc`.
2. *Repositories → minipc* : l'état doit être correct (pas d'erreur SFTP ni de mot de passe).
3. Lancer chaque plan à la main (*Plans → <plan> → Backup now*), en commençant par `hote` (aucun arrêt) puis `vaultwarden`.
   ⚠ Un lancement manuel arrête aussi les conteneurs du plan : faire `jellyfin` quand personne ne regarde.
4. Vérifier :
   ```bash
   ls -l ~/Homelab/compose/monitoring/data/textfile/        # backrest-<plan>.prom pour chaque plan réussi
   docker ps --format '{{.Names}}\t{{.Status}}' | sort      # tout est relancé (Up quelques minutes)
   ls ~/Homelab/compose/backrest/data/backrest/etat-hooks/  # vide (un fichier = des conteneurs pas relancés)
   ```
   Dans Grafana / Prometheus : `homelab_sauvegarde_derniere_reussite_timestamp_seconds{outil="backrest"}`.
5. Test de notification : *Plans → infra → Edit*, ajouter temporairement un chemin inexistant, *Backup now* → message ntfy
   « Sauvegarde infra : problème ». Retirer le chemin.

## Restauration
Dans l'interface : *Plans → <plan> → snapshot → Restore*, cible **`/restauration/<nom>`** (le seul dossier inscriptible, =
`data/restauration/` sur l'hôte). Les propriétaires et droits d'origine sont conservés. Puis copier à la main au bon endroit,
stack arrêtée.

### Test régulier : Vaultwarden
1. Restaurer le dernier snapshot du plan `vaultwarden` vers `/restauration/vw-test`.
2. Sur le Mini PC :
   ```bash
   cd ~/Homelab/compose/backrest/data/restauration/vw-test/sources/vaultwarden
   sqlite3 db.sqlite3 "PRAGMA integrity_check; SELECT count(*) FROM users; SELECT count(*) FROM ciphers;"
   cmp rsa_key.pem ~/Homelab/compose/vaultwarden/data/rsa_key.pem && echo "rsa_key identique"
   ```
3. Instance jetable : procédure « Test de restauration » de [`compose/vaultwarden/README.md`](../vaultwarden/README.md),
   avec ce dossier en `/data`.
4. Nettoyer : `docker exec backrest rm -rf /restauration/vw-test` (les fichiers restaurés gardent leurs propriétaires d'origine,
   dont root : le compte administrateur ne peut pas tout supprimer lui-même).

### Sans Backrest (Mini PC perdu)
Le dépôt est un dépôt restic standard, lisible depuis n'importe quelle machine avec restic :
```bash
export RESTIC_REPOSITORY='sftp://backup_minipc@<ip-du-nas>:<port-ssh>//<partage>/minipc'
export RESTIC_PASSWORD='<mot de passe : SOPS, Vaultwarden ou papier>'
restic snapshots --tag plan:vaultwarden
restic restore latest --tag plan:vaultwarden --target /tmp/restauration
```
Reconstruction complète : Debian + Docker, `git clone` du dépôt, clé age (copie du PC, ou nouvelle clé + `sops updatekeys`),
restauration des plans dans `compose/<stack>/…`, puis `scripts/compose-up.sh <stack>`.

## Ajouter une stack
1. Monter son dossier de données en `:ro` sous `/sources/<plan>` dans `compose.yaml`.
2. Créer le plan dans l'interface (chemin `/sources/<plan>`, planning entre 05:00 et 06:00, rétention), ou dans `config.json`.
3. Si elle a une base de données : ajouter ses conteneurs dans `CONTENEURS` de [`hooks/backrest-hook.sh`](hooks/backrest-hook.sh)
   **et** dans `-allowPOST` de `socket-proxy-backrest` (sinon HTTP 403 : sauvegarde annulée, notification).
4. `scripts/compose-up.sh backrest` (recrée backrest pour le nouveau montage).

Supprimer un plan : supprimer aussi `compose/monitoring/data/textfile/backrest-<plan>.prom`, sinon `SauvegardeEnRetard` se déclenche.

## Retrait de l'ancien script Vaultwarden
Après un test de restauration réussi depuis Backrest (voir plus haut) :
1. `crontab -e` : supprimer la ligne `vaultwarden-backup.sh`.
2. `rm ~/Homelab/compose/monitoring/data/textfile/vaultwarden.prom` (l'alerte `SauvegardeVaultwardenInconnue` reste satisfaite par
   la métrique de Backrest, `tache="vaultwarden"`).
3. Les archives déjà sur le Synology peuvent rester (elles ne sont plus renouvelées).

## Retrait de Portabase
Portabase ne sauvegardait que le volume d'Arcane, repris par le plan `arcane`. Les dossiers `compose/portabase*` sont retirés
du dépôt ; sur le Mini PC, **avant** que ce commit y arrive (push → déploiement automatique), arrêter les stacks tant que
leurs fichiers compose sont encore là :
```bash
scripts/compose-up.sh portabase-agent portabase down
```
Si le commit est déjà arrivé : `docker compose -p portabase-agent down` et `docker compose -p portabase-dashboard down`
(noms de projet des anciens compose). Ensuite, avec un compte sudoer (`postgres-data` appartient à 70:70) :
`rm -rf ~/Homelab/compose/portabase ~/Homelab/compose/portabase-agent`, et supprimer le host override `portabase.<domaine>` dans pfSense.

## Dépannage
| Symptôme | Cause probable |
|---|---|
| `Permission denied (publickey)` / `ssh: connect` dans *Repositories* | Clé absente de `authorized_keys`, `from=` différent de l'IP du Mini PC, SFTP non autorisé pour `backup_minipc` |
| `Host key verification failed` | `data/ssh/known_hosts` vide ou faux : refaire `ssh-keyscan` |
| `wrong password or no key found` | `RESTIC_PASSWORD_MINIPC` différent de celui de l'initialisation |
| `path /sources/... does not exist` | Montage absent : `scripts/compose-up.sh backrest` après modification du compose |
| Sauvegarde annulée, log du hook : `HTTP 403` | Conteneur absent de `-allowPOST` du socket-proxy |
| Conteneur resté arrêté | `cat data/backrest/etat-hooks/*.arretes`, puis `docker start <nom>` ; le prochain passage réessaie aussi |
| Dépôt verrouillé (`repository is already locked`) | `autoUnlock` est actif ; sinon *Repositories → minipc → Unlock* |
| Interface : écran de réglages à chaque visite | Aucun compte créé : en créer un |
