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

# Données : restaurer le dernier snapshot du plan `vaultwarden` de Backrest (db.sqlite3, -wal, -shm et rsa_key.pem ensemble)
cp -a /chemin/restauration/sources/vaultwarden/. data/
# data/ et tls/ doivent appartenir à l'UID 1000 (= conteneur). Le compte administrateur l'est normalement
# (vérifier : id -u), donc rien à faire et pas de sudo. Sinon : chown -R 1000:1000 data tls
chmod 600 tls/key.pem

cd ../.. && scripts/compose-up.sh vaultwarden
```

## Sauvegarde
[Backrest](../backrest/README.md), plan `vaultwarden` : chaque nuit à 5h, conteneur arrêté pendant la copie (base SQLite et WAL
cohérents), dépôt restic chiffré sur le Synology, rétention 30 j / 8 sem / 12 mois. Alerte `SauvegardeEnRetard` au-delà de 26 h.

L'ancien script `scripts/vaultwarden-backup.sh` (cron 3h15, archive + rsync vers le Synology) a été retiré le 2026-10-26,
après un test de restauration réussi depuis Backrest.

### Test de restauration (à refaire régulièrement)
Procédure : « Test régulier : Vaultwarden » dans le [README de Backrest](../backrest/README.md). Dernier test : 2026-10-26,
snapshot du jour, `integrity_check` ok, 1 utilisateur et 563 éléments comme la base en service, `rsa_key.pem` présente.

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

## Derrière Traefik (2026-10)
Vaultwarden est publié par Traefik sur `vault.<DOMAIN>`, en HTTP sur le réseau `proxy` : Traefik termine le TLS avec le
certificat wildcard Let's Encrypt. Plus de port 8443 publié, plus de `ROCKET_TLS` ni de certificat auto-signé.
`/admin` a son propre router, limité aux postes d'admin (`lan-admin@docker`) en plus de `ADMIN_TOKEN`.

- `DOMAIN` vient de `compose/commun.sops.env` (domaine racine) ; le compose en déduit `https://vault.<DOMAIN>`.
  **Ne pas** redéfinir `DOMAIN` dans `secrets.sops.env` : la valeur de la stack est prioritaire et casserait la règle Traefik.
- L'URL doit rester identique à l'ancienne (WebAuthn/passkeys liés au domaine).
- Bascule : `scripts/compose-up.sh vaultwarden`, puis déplacer `vault` vers le Mini PC dans les host overrides pfSense,
  puis retirer l'hôte de npmplus. Le dossier `tls/` peut être supprimé une fois validé.
- Le test de restauration plus haut utilise encore le TLS auto-signé : il reste valable tel quel (instance jetable).
