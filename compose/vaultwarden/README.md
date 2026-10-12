# Vaultwarden (Mini PC)

Migration depuis le CT Proxmox : IP et règles pare-feu dans `private/`.

## Secrets (`secrets.sops.env`, chiffré)
```dotenv
ADMIN_TOKEN=$argon2id$v=19$m=...   # hash argon2 du jeton admin (voir ci-dessous)
DOMAIN=https://...                 # URL exacte actuelle du coffre (passkeys/FIDO2 liés au domaine)
BIND_IP=...                        # IP LAN du Mini PC sur laquelle le port est publié
```
Format dotenv de SOPS : **pas de guillemets** autour des valeurs (ils seraient conservés tels quels).

## Jeton admin (`/admin`)
L'ancien CT avait `ADMIN_TOKEN` vide, donc l'interface `/admin` était désactivée. On en crée un fort :
```bash
openssl rand -base64 48                 # jeton en clair : à ranger dans le gestionnaire de mots de passe
docker run --rm -it vaultwarden/server:1.37.0 /vaultwarden hash --preset owasp
# coller le jeton aux deux invites ; copier la ligne $argon2id$... dans secrets.sops.env
```
Seul le **hash** va dans `secrets.sops.env` ; le jeton en clair sert à se connecter sur `/admin`.

## Premier démarrage
```bash
cd compose/vaultwarden
mkdir -p data tls
sops secrets.sops.env        # créer le fichier avec les 3 variables ci-dessus

# Certificat TLS interne auto-signé (hors Git : *.pem est ignoré)
sops exec-env secrets.sops.env 'openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes \
  -keyout tls/key.pem -out tls/cert.pem -days 3650 -subj "/CN=vaultwarden" \
  -addext "subjectAltName=DNS:vaultwarden,IP:$BIND_IP"'

# Données : base sauvegardée avec `sqlite3 .backup` (sans fichiers -wal/-shm) + rsa_key.pem
cp /chemin/vw-backup/db.sqlite3 data/
cp /chemin/vw-backup/rsa_key.pem data/
# data/ et tls/ doivent appartenir à l'UID 1000 (= conteneur). Le compte administrateur l'est normalement
# (vérifier : id -u), donc rien à faire et pas de sudo. Sinon : chown -R 1000:1000 data tls
chmod 600 tls/key.pem

cd ../.. && scripts/compose-up.sh vaultwarden
```

## Sauvegarde
Ne jamais copier `db.sqlite3` à chaud : utiliser `sqlite3 .backup`.
