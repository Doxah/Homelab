# SoulSync + slskd (Mini PC)

Stack musique « Spotify selfhost » : [SoulSync](https://github.com/Nezreka/SoulSync) découvre la musique (Spotify, Deezer, ListenBrainz…),
gère la wishlist et les artistes suivis, télécharge via [slskd](https://github.com/slskd/slskd) (Soulseek), tague et range les fichiers
dans la bibliothèque musicale lue par Jellyfin.

```
Spotify / Deezer / ListenBrainz ──► SoulSync ──► slskd ──► ./downloads ──► SoulSync (tags, rangement) ──► MUSIC_DIR ──► Jellyfin
```

## Secrets (`secrets.sops.env`, chiffré)
Le fichier est livré **pré-rempli** avec une ligne commentée par variable : `sops compose/soulsync/secrets.sops.env`, décommenter, remplacer.

| Variable | Rôle |
|---|---|
| `BIND_IP` | IP LAN du Mini PC (ports 8008 et 5030 publiés uniquement dessus) |
| `MUSIC_DIR` | Chemin absolu de la bibliothèque musicale (montage NAS lu par Jellyfin) |
| `SLSKD_SLSK_USERNAME` / `SLSKD_SLSK_PASSWORD` | Compte du réseau Soulseek (créé à la 1re connexion si le nom est libre) |
| `SLSKD_USERNAME` / `SLSKD_PASSWORD` | Connexion à l'interface web slskd |
| `SLSKD_JWT_KEY` | `openssl rand -base64 48` |
| `SLSKD_API_KEY` | `openssl rand -hex 32` — à recopier dans SoulSync |

Format dotenv de SOPS : **pas de guillemets** autour des valeurs.

## Premier démarrage
```bash
cd compose/soulsync
mkdir -p config data storage logs downloads staging slskd
# Tout appartient à l'UID 1000 (= conteneurs). Normalement le compte administrateur l'est déjà (id -u) : pas de sudo.
ls -ln .
# MUSIC_DIR doit être inscriptible par l'UID 1000 (SoulSync y écrit, slskd le lit en :ro)
sops exec-env secrets.sops.env 'ls -lnd "$MUSIC_DIR" && touch "$MUSIC_DIR/.soulsync-test" && rm "$MUSIC_DIR/.soulsync-test"'

cd ../.. && scripts/compose-up.sh soulsync pull && scripts/compose-up.sh soulsync
docker logs -f soulsync      # les « WARNING: ... not writable » de l'audit gosu sont attendus (voir compose.yaml)
```

## Configuration de SoulSync (`https://<url>` via npmplus, ou `http://<BIND_IP>:8008`)
1. **Settings → Connections → Soulseek** : URL `http://slskd:5030` (réseau interne de la stack), clé = `SLSKD_API_KEY`.
2. **Settings → Downloads** : dossier de téléchargement `/app/downloads`, **Transfer** `/app/Transfer`.
3. **Settings → Connections → Jellyfin** : URL de Jellyfin par l'IP du Mini PC (pas `localhost` : ce serait le conteneur), clé API Jellyfin.
   Dans Jellyfin, une bibliothèque *Musique* pointant sur le même dossier que `MUSIC_DIR`.
4. **Spotify (optionnel, meilleure découverte)** : créer une appli sur [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard),
   redirect URI **`https://<url de SoulSync>/callback`** (HTTPS via npmplus : le callback passe par le port 8008, pas besoin de 8888),
   même URI dans **Settings → Connections → Spotify** avec Client ID / Secret.
   Sans npmplus, Spotify n'accepte que `http://127.0.0.1:8888/callback` → il faudrait publier 8888 et un tunnel SSH.

## npmplus
| Hôte | Destination | Options |
|---|---|---|
| SoulSync | `http://<IP Mini PC>:8008` | **Websockets Support** activé (mises à jour en direct via Socket.IO) |
| slskd (optionnel) | `http://<IP Mini PC>:5030` | Websockets Support activé (SignalR) |

Pare-feu : n'autoriser que npmplus vers 8008/5030 sur le Mini PC.

## Moindre privilège
Les deux conteneurs tournent en `1000:1000`, `cap_drop: ALL`, `no-new-privileges`, système de fichiers en lecture seule.

- **SoulSync** : l'image démarre normalement en root (usermod + gosu) ; avec `user: 1000:1000` = `PUID` par défaut, l'entrypoint saute ces étapes.
  Écritures hors volumes → `tmpfs` (`/app/Stream`, `$HOME`). Si une fonction échoue avec `Read-only file system`, ajouter le chemin en `tmpfs`
  (temporaire) ou en volume (persistant), puis le noter dans `compose.yaml`.
- **slskd** : mode `user:` natif de l'image (ne pas définir `PUID`/`PGID` : l'entrypoint refuse les deux à la fois).

Vérifier :
```bash
for c in soulsync slskd; do docker exec $c id; docker inspect -f '{{.Name}} user={{.Config.User}} ro={{.HostConfig.ReadonlyRootfs}} capdrop={{.HostConfig.CapDrop}}' $c; done
```

## Sauvegarde
À sauvegarder : `data/` (bases SQLite **en WAL** : copier avec `sqlite3 .backup`, comme pour Vaultwarden), `config/`, `slskd/slskd.yml`.
`storage/` (cache d'images), `logs/` et `downloads/` sont reconstructibles. La bibliothèque `MUSIC_DIR` est sur le NAS.

## Notes
- Partager sa bibliothèque sur Soulseek est la norme (sinon certains pairs refusent ou mettent en file d'attente) : `MUSIC_DIR` est partagé en lecture seule.
- Port Soulseek entrant 50300 non publié (double NAT Livebox → pfSense) : ça marche, mais avec moins de pairs joignables.
- Mise à jour : changer les tags d'image, puis `scripts/compose-up.sh soulsync pull && scripts/compose-up.sh soulsync`.
