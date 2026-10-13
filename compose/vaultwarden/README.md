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
sops secrets.sops.env        # créer le fichier avec les 3 variables ci-dessus (BIND_IP = IP LAN, pas 127.0.0.1 : sinon injoignable depuis le reverse proxy)

# Certificat TLS interne auto-signé (hors Git : *.pem est ignoré)
sops exec-env secrets.sops.env 'openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes \
  -keyout tls/key.pem -out tls/cert.pem -days 3650 -subj "/CN=vaultwarden" \
  -addext "subjectAltName=DNS:vaultwarden,DNS:${DOMAIN#https://},IP:$BIND_IP"'

# Données : base sauvegardée avec `sqlite3 .backup` (sans fichiers -wal/-shm) + rsa_key.pem
cp /chemin/vw-backup/db.sqlite3 data/
cp /chemin/vw-backup/rsa_key.pem data/
# data/ et tls/ doivent appartenir à l'UID 1000 (= conteneur). Le compte administrateur l'est normalement
# (vérifier : id -u), donc rien à faire et pas de sudo. Sinon : chown -R 1000:1000 data tls
chmod 600 tls/key.pem

cd ../.. && scripts/compose-up.sh vaultwarden
```

## Sauvegarde
Ne jamais copier `db.sqlite3` à chaud : les modifications récentes sont dans `db.sqlite3-wal` tant qu'il n'y a pas eu de checkpoint
(constaté sur le CT : `db.sqlite3` vieux de deux semaines, WAL de 3 Mo). On utilise `sqlite3 .backup`, qui produit une base complète et cohérente.

Script : [`scripts/vaultwarden-backup.sh`](../../scripts/vaultwarden-backup.sh) (base + `rsa_key.pem` + `attachments/`/`sends/` s'ils existent,
contrôle d'intégrité, archive datée, rétention locale, copie rsync vers le NAS).

Prérequis (une fois, par un compte sudoer) : `apt install sqlite3 rsync`.
Variables à ajouter dans `secrets.sops.env` :
```dotenv
# BACKUP_DIR=/home/<utilisateur>/backups/vaultwarden
# BACKUP_KEEP_DAYS=14
# RSYNC_DEST=syno-backup:/volume1/<partage>/vaultwarden
```

### Copie vers le Synology (rsync via SSH, clé dédiée)
Sur le Mini PC, avec l'utilisateur qui lance la stack :
```bash
ssh-keygen -t ed25519 -f ~/.ssh/vw-backup -N "" -C "vaultwarden-backup@mini-pc"   # sans phrase de passe : lancé par cron
cat >> ~/.ssh/config <<'CFG'
Host syno-backup
    HostName <ip-du-nas>
    Port <port-ssh>
    User <utilisateur-de-sauvegarde>
    IdentityFile ~/.ssh/vw-backup
    IdentitiesOnly yes
CFG
chmod 600 ~/.ssh/config
```
Sur le NAS (DSM 7.2) :
1. Panneau de configuration → Terminal & SNMP : SSH activé.
2. Panneau de configuration → Utilisateur → Avancé : activer le service d'accueil de l'utilisateur.
3. Services de fichiers → rsync : activer le service rsync ; Privilèges des applications → rsync : autoriser l'utilisateur de sauvegarde. Droits en écriture sur le dossier cible uniquement.
4. En SSH avec un compte administrateur puis `sudo -i`, installer la clé publique :
   ```bash
   H=/var/services/homes/<utilisateur-de-sauvegarde>
   mkdir -p $H/.ssh
   echo 'from="<ip-du-mini-pc>",no-pty,no-port-forwarding,no-agent-forwarding,no-X11-forwarding <contenu de vw-backup.pub>' >> $H/.ssh/authorized_keys
   chown -R <utilisateur-de-sauvegarde>:users $H/.ssh
   chmod 755 $H && chmod 700 $H/.ssh && chmod 600 $H/.ssh/authorized_keys
   ```
Test depuis le Mini PC : `rsync -av /etc/hostname syno-backup:/volume1/<partage>/vaultwarden/` (la 1re connexion demande de valider l'empreinte du NAS).

Planification (crontab de l'utilisateur qui lance la stack) :
```cron
15 3 * * * /home/<utilisateur>/homelab/scripts/vaultwarden-backup.sh >> /home/<utilisateur>/backups/vaultwarden.log 2>&1
```

### Test de restauration (à faire après la mise en place, puis régulièrement)
```bash
mkdir -p /tmp/vw-restore && tar xzf ~/backups/vaultwarden/vaultwarden-<date>.tar.gz -C /tmp/vw-restore
sqlite3 /tmp/vw-restore/db.sqlite3 'PRAGMA integrity_check; SELECT count(*) FROM ciphers;'
```
Test complet : lancer une instance jetable sur ces données (autre port, `SIGNUPS_ALLOWED=false`), s'y connecter et vérifier le nombre d'entrées.

## Bascule depuis le CT
Pas d'accès externe : Vaultwarden n'est joint qu'en interne, via npmplus. Le CT n'avait ni `DOMAIN`, ni SMTP, ni `config.json`, ni pièces jointes.

1. **Arrêter Vaultwarden dans le CT** (plus aucune écriture) : `systemctl list-units | grep -i vault` puis `systemctl stop <service>`.
2. **Copie finale** dans le CT, **chemins absolus uniquement** (`sqlite3` crée une base vide si le fichier source n'existe pas, et `.backup` copie alors cette base vide sans erreur) :
   ```bash
   sqlite3 /opt/vaultwarden/data/db.sqlite3 "SELECT count(*) FROM users; SELECT count(*) FROM ciphers;"   # 1 et ~550
   sqlite3 /opt/vaultwarden/data/db.sqlite3 ".backup '/root/vw-final.sqlite3'"
   sqlite3 /root/vw-final.sqlite3 "PRAGMA integrity_check; SELECT count(*) FROM users; SELECT count(*) FROM ciphers;"
   ```
   Transfert depuis le T130 : `pct pull <id> /root/vw-final.sqlite3 /root/vw-final.sqlite3`, puis `scp` vers `/tmp/` du Mini PC (`pct pull` ne copie qu'un fichier).
3. **Remplacer la copie de test** sur le Mini PC :
   ```bash
   scripts/compose-up.sh vaultwarden stop     # toujours via le script : un `docker compose` nu n'a pas les secrets
   rm -f compose/vaultwarden/data/db.sqlite3*  # db + -wal + -shm de test, sinon le WAL de test serait rejoué sur la nouvelle base
   cp /tmp/vw-final.sqlite3 compose/vaultwarden/data/db.sqlite3 && ls -ln compose/vaultwarden/data
   scripts/compose-up.sh vaultwarden
   ```
4. **npmplus** : proxy host du coffre → schéma `https`, IP du Mini PC, port `8443`.
5. **Vérifier** dans `/admin` → Users (1 compte, ~550 entrées), puis depuis le navigateur, l'appli bureau et le mobile : connexion, synchro, créer une entrée de test et la retrouver sur un autre client.
6. **Garder le CT arrêté 1 à 2 semaines** sans le démarrer au boot (`pct set <id> -onboot 0` sur le T130), puis le supprimer.

Retour arrière : redémarrer le CT et remettre l'ancienne destination dans npmplus. Tout ce qui a été modifié sur le Mini PC entre-temps est perdu.
