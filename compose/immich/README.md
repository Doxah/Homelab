# Immich (Mini PC)

Photos et vidéos auto-hébergées (sauvegarde automatique des téléphones, reconnaissance faciale, recherche par le contenu).
Réinstallation de l'ancienne instance (compose officiel par défaut, Immich v2) dans le dépôt, en **v3**.

```
LAN / VPN ───────────────────────────────┐
Internet ──► Cloudflare ──► cloudflared ─┴─► Traefik immich.<domaine> ──► immich_server ──► immich_machine_learning (default)
                                                                            │
                                                                            └──► immich_postgres + immich_redis (réseau « interne », sans Internet)
```

## Choix
| Sujet | Choix | Pourquoi |
|---|---|---|
| Base | Compose officiel v3.3.5 et sa variante rootless | Même images, mêmes noms de conteneurs que l'ancien compose : la base v2 est reprise telle quelle |
| Version | `v3.3.5` figée (au lieu de `IMMICH_VERSION=v2`/`release`) | Mises à jour proposées par Renovate, jamais de saut de version majeure à l'insu |
| Secrets | `UPLOAD_LOCATION`, `DB_PASSWORD` dans SOPS ; plus de `.env` ni d'`env_file` | Rien en clair sur le disque ; le reste (utilisateur, nom de la base) est en dur dans `compose.yaml` |
| Accès | `immich.<domaine>` par Traefik, sans `lan-admin` : LAN, VPN et Internet (tunnel Cloudflare) | Appli mobile et famille. Plus de port 2283 publié |
| Tunnel Cloudflare | Route `immich` dans le tunnel `homelab` (stack `cloudflared`) | Accès depuis l'extérieur sans VPN. Limite de 100 Mo par requête : voir « Accès depuis Internet » |
| Transcodage | Intel QuickSync (`/dev/dri`, groupe `render`), comme Jellyfin | À activer aussi dans l'interface |
| Machine learning | CPU | OpenVINO (iGPU) possible plus tard, voir le commentaire dans `compose.yaml` |
| Sauvegarde de la base | Dumps automatiques d'Immich dans `./data/db-dumps` (disque local) | Copie cohérente sans arrêter la stack ; Backrest les lit sans secret |

## Moindre privilège
| Conteneur | Réglages | Exception |
|---|---|---|
| immich_server | 1000:1000, `cap_drop: ALL`, `no-new-privileges`, limites | `/dev/dri` + groupe `render` (QuickSync) ; pas de `read_only` (non prévu par l'upstream) |
| immich_machine_learning | 1000:1000, `cap_drop: ALL`, `no-new-privileges`, limites | pas de `read_only` ; réseau `default` pour télécharger les modèles |
| immich_postgres | 1000:1000 (au lieu de root → `postgres`), `cap_drop: ALL`, `no-new-privileges`, réseau interne | pas de `read_only` |
| immich_redis (Valkey) | 1000:1000, `cap_drop: ALL`, `read_only`, `/data` en tmpfs, réseau interne | — |

Vérifier : `docker top immich_server -o pid,user,comm` (tout en 1000) et
`docker inspect -f '{{.Name}} user={{.Config.User}} capdrop={{.HostConfig.CapDrop}}' immich_server immich_machine_learning immich_postgres immich_redis`.

## Secrets (`secrets.sops.env`)
⚠ Livré **pré-rempli mais pas encore chiffré** (pas de `sops` dans l'environnement où il a été créé) : le chiffrer **avant** de
le remplir, depuis le PC Windows :
```powershell
sops encrypt -i compose/immich/secrets.sops.env    # chiffre les lignes commentées (clés de .sops.yaml)
sops compose/immich/secrets.sops.env               # décommenter, remplacer, supprimer la ligne « ⚠ PAS ENCORE CHIFFRÉ »
```
Le hook pre-commit `sops-chiffre` refuse le commit tant qu'il n'est pas chiffré.

| Variable | Rôle |
|---|---|
| `UPLOAD_LOCATION` | Dossier de la bibliothèque sur le Mini PC (ancien : `/media/Immich`), monté en `/data` |
| `DB_PASSWORD` | Mot de passe PostgreSQL, `A-Za-z0-9` uniquement. **Reprise : même valeur que l'ancien `.env`** (il est inscrit dans la base) |

`DOMAIN` vient de `compose/commun.sops.env`.

## Mise en service
Chemins : le dépôt est cloné dans `~/Homelab` sur le Mini PC. Les commandes `sudo` se font avec un compte sudoer
(`administrateur` ne l'est pas), puis on revient en `administrateur` pour le reste.

### A. Reprise de l'ancienne installation (v2 → v3)
1. **Arrêter l'ancienne stack** et relever ses valeurs :
   ```bash
   cd <ancien dossier immich> && grep -E 'UPLOAD_LOCATION|DB_DATA_LOCATION|DB_PASSWORD|IMMICH_VERSION' .env
   docker compose down
   ```
   Reporter `UPLOAD_LOCATION` et `DB_PASSWORD` dans le fichier SOPS (voir plus haut), commit, push.
2. **Copie de sécurité de la base** (dossier `DB_DATA_LOCATION`, `./postgres` par défaut), avant toute migration :
   ```bash
   sudo cp -a <ancien dossier immich>/postgres <ancien dossier immich>/postgres.v2-sauvegarde
   ```
   Immich a aussi ses propres dumps dans `<UPLOAD_LOCATION>/backups/` (un par jour, 14 gardés).
3. **Déplacer la base** dans la stack et la donner à l'UID 1000 (avant : `postgres` = 999 dans le conteneur) :
   ```bash
   sudo mv <ancien dossier immich>/postgres ~administrateur/Homelab/compose/immich/postgres-data
   sudo chown -R 1000:1000 ~administrateur/Homelab/compose/immich/postgres-data
   ```
4. **Bibliothèque** : elle doit être inscriptible par 1000:1000.
   ```bash
   ls -ln <UPLOAD_LOCATION> | head      # propriétaire actuel (l'ancien compose tournait en root)
   sudo chown -R 1000:1000 <UPLOAD_LOCATION>   # disque local seulement
   ```
   Si c'est un **montage NAS**, le `chown` ne s'applique pas : régler le montage (CIFS : `uid=1000,gid=1000` dans `/etc/fstab` ;
   NFS : droits/squash côté NAS). Test dans tous les cas :
   ```bash
   docker run --rm --user 1000:1000 -v <UPLOAD_LOCATION>:/d busybox:1.37 sh -c 'touch /d/upload/.t && rm /d/upload/.t && echo OK'
   ```
5. **Dossiers locaux** ; les anciens dumps sont repris (avec le marqueur `.immich` que le serveur vérifie au démarrage) :
   ```bash
   cd ~/Homelab/compose/immich
   mkdir -p data/model-cache data/db-dumps
   cp -a <UPLOAD_LOCATION>/backups/. data/db-dumps/
   ```
6. **Vérifier l'extension vectorielle** avant de lancer le serveur v3 (la v3 ne supporte plus pgvecto.rs) :
   ```bash
   cd ~/Homelab
   scripts/compose-up.sh immich config --quiet && scripts/compose-up.sh immich pull
   scripts/compose-up.sh immich up -d database
   docker exec immich_postgres psql -U postgres -d immich -c "select extname, extversion from pg_extension;"
   ```
   `vchord` présent : continuer. Seulement `vectors` : démarrer d'abord une fois en v2 (tags `v2.7.5` dans `compose.yaml`) pour
   que la migration vers VectorChord se fasse, puis repasser en `v3.3.5`.
7. **Lancer** : `scripts/compose-up.sh immich`, puis `docker logs -f immich_server` (migrations de la base au premier démarrage,
   puis `Immich Server is listening`). Comparer le nombre de photos / personnes avec l'ancienne instance.
8. Nettoyage, une fois validé : `docker volume rm immich_model-cache` (ancien volume nommé), l'ancien dossier et
   `postgres.v2-sauvegarde` (compte sudoer), les anciens dumps dans `<UPLOAD_LOCATION>/backups/`.

### B. Nouvelle installation
```bash
cd ~/Homelab/compose/immich
mkdir -p data/model-cache data/db-dumps postgres-data            # AVANT le 1er lancement : sinon Docker les crée en root
sudo install -d -o 1000 -g 1000 <UPLOAD_LOCATION>                # compte sudoer, si le dossier n'existe pas
cd ~/Homelab && scripts/compose-up.sh immich config --quiet && scripts/compose-up.sh immich pull && scripts/compose-up.sh immich
```
Ouvrir `https://immich.<domaine>` tout de suite : **le premier compte créé est administrateur**.

### DNS
pfSense → *Services → DNS Resolver → Host Overrides* : `immich.<domaine>` → IP du Mini PC.
Retirer l'ancienne règle pare-feu vers le port 2283 s'il y en avait une.

### Accès depuis Internet (tunnel Cloudflare)
Route à ajouter dans le tunnel `homelab` (règle générale : [`compose/cloudflared/README.md`](../cloudflared/README.md)) :
Zero Trust → Networks → Tunnels → *homelab* → Public Hostname → Add :

| Champ | Valeur |
|---|---|
| Subdomain / Domain | `immich` / `<domaine>` |
| Service | `HTTPS` — `traefik:8443` |
| Additional settings → TLS → **Origin Server Name** | `immich.<domaine>` (sinon refusé par Traefik, `sniStrict`) |

Aucun changement dans les compose : le router Traefik `immich` n'a pas `lan-admin`, il accepte le trafic de cloudflared.

**Même nom, deux chemins** : à la maison, le host override pfSense envoie `immich.<domaine>` directement sur Traefik
(pas de Cloudflare, pas de limite) ; dehors, le DNS public pointe sur le tunnel. Une seule URL dans l'appli mobile.

**Limite de 100 Mo** par requête chez Cloudflare (plan gratuit, non modifiable) : depuis l'extérieur, une vidéo plus lourde
échoue à l'envoi. La sauvegarde du téléphone la reprend une fois à la maison (ou par le VPN) ; consulter et partager
fonctionne partout.

Durcissement conseillé (Immich est alors exposé sur Internet) :
- comptes avec des mots de passe forts, inscription publique fermée (par défaut, seul l'admin crée les comptes) ;
- Cloudflare → *Security → WAF → Custom rules* : bloquer les pays autres que la France sur `immich.<domaine>` ;
- tester depuis la 4G : `curl -sI https://immich.<domaine>/api/server/ping`.

### Réglages dans l'interface (Administration → Paramètres)
| Réglage | Valeur |
|---|---|
| Paramètres du serveur → Domaine externe | `https://immich.<domaine>` (liens de partage) |
| Transcodage vidéo → Accélération matérielle | Quick Sync, accélération du décodage activée |
| Sauvegarde de la base | Activée (par défaut), 02:00, garder 14 : écrit dans `./data/db-dumps` |
| Appli mobile → URL du serveur | `https://immich.<domaine>` (même URL partout, voir « Accès depuis Internet ») |

### Après la mise en service
- **Supervision** : décommenter la ligne `immich` dans `compose/monitoring/prometheus/cibles/https.yml` (sonde `/api/server/ping`).
- **Déploiement automatique** : facultatif, ajouter `immich` à [`compose/deploiement-auto.txt`](../deploiement-auto.txt)
  (pas avant : sans `postgres-data` et les secrets sur le Mini PC, le déploiement échouerait).
- **Sauvegarde** : voir ci-dessous.

## Sauvegardes
| Quoi | Où | Sauvegardé par |
|---|---|---|
| Base (dumps quotidiens d'Immich) | `compose/immich/data/db-dumps` | Backrest : à ajouter (plan `immich`, ci-dessous) |
| Bibliothèque (originaux) | `UPLOAD_LOCATION` | Pas encore : avec le NAS central (feuille de route), le Synology n'a que ~500 Go libres |
| Miniatures, vidéos transcodées, modèles ML | `UPLOAD_LOCATION/thumbs`, `encoded-video`, `data/model-cache` | Jamais : régénérables |
| `postgres-data` | — | Jamais en direct : copie à chaud incohérente, les dumps suffisent |

Plan Backrest à ajouter (procédure « Ajouter une stack » de [`compose/backrest/README.md`](../backrest/README.md)) :
- monter `../immich/data/db-dumps:/sources/immich:ro` dans `compose/backrest/compose.yaml` ;
- plan `immich`, chemin `/sources/immich`, 05:50, rétention 7 j / 4 sem / 6 mois ;
- **aucun conteneur à arrêter** (les dumps sont déjà des fichiers terminés à 05:50) : rien à changer dans les hooks ni le socket-proxy.

Restauration de la base depuis un dump : procédure officielle
(<https://docs.immich.app/administration/backup-and-restore>), avec `immich_postgres` et `postgres-data` vide.

## Mises à jour
`immich-server` et `immich-machine-learning` doivent **toujours avoir la même version**. Avant une version majeure (v4…),
lire les notes de version : le compose officiel peut changer (images Postgres/Valkey). Les applis mobiles doivent suivre
la version du serveur (même majeure et mineure).

## Dépannage
| Symptôme | Cause probable |
|---|---|
| `EACCES` / `permission denied` sur `/data/...` | `UPLOAD_LOCATION` pas inscriptible par 1000:1000 (voir étape A.4) |
| `Failed to read "/data/backups/.immich"` (ou un autre dossier) | Marqueur absent : reprendre l'étape A.5, ou `touch data/db-dumps/.immich` sur une installation neuve |
| Postgres : `data directory ... has wrong ownership` / `could not open file` | `postgres-data` pas en 1000:1000 (étape A.3) |
| Postgres : `password authentication failed` | `DB_PASSWORD` différent de celui de l'ancienne base |
| ML : `Permission denied: '/cache/...'` | `data/model-cache` créé par Docker en root : `sudo chown -R 1000:1000 data/model-cache` |
| Vidéos du téléphone qui n'arrivent pas (hors de la maison) | Envoi par le tunnel Cloudflare (100 Mo max) : elles partent au retour sur le LAN/VPN |
| `502` / « Bad gateway » depuis Internet seulement | Route du tunnel sans *Origin Server Name* `immich.<domaine>`, ou service en `http://` au lieu de `HTTPS` |
| `502` depuis Internet alors que la route est bonne | Un ancien connecteur cloudflared (autre serveur) tourne encore sur le même tunnel : Cloudflare répartit le trafic entre les connecteurs. Zero Trust → Tunnels → *homelab* → Connectors : il ne doit y avoir que le Mini PC (vécu en oct. 2026) |
| Transcodage matériel en échec | GID de `render` différent de 105 : `getent group render` et adapter `group_add` |
| ML : `connection to ('::', 3003) failed: [Errno 97] Address family not supported` | IPv6 désactivé sur l'hôte : `IMMICH_HOST: 0.0.0.0` (déjà en place dans `compose.yaml`) |
| Le serveur refuse de démarrer après la mise à jour v3 | Extension `vectors` (pgvecto.rs) : voir étape A.6 |
