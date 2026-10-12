# GLPI (Mini PC)

GLPI 12 (image officielle `glpi/glpi`) + MariaDB 11.4. Installation de la base automatique au premier démarrage.

Points propres à GLPI 12 :
- Les appels sortants vers des **réseaux internes** sont bloqués par défaut (webhooks, collecteurs mail, intégrations). À autoriser explicitement si GLPI doit joindre un service du LAN.
- Les plugins doivent être compatibles 12 : vérifier avant d'en installer un.
- Branche jeune : suivre les versions correctives 12.0.x.

## Secrets (`secrets.sops.env`, chiffré)
```dotenv
GLPI_DB_PASSWORD=...   # mot de passe de l'utilisateur MariaDB glpi
```
Format dotenv de SOPS : **pas de guillemets** autour des valeurs.
Générer une valeur sans caractères spéciaux gênants : `openssl rand -hex 32`.

Le mot de passe root MariaDB est aléatoire (`MARIADB_RANDOM_ROOT_PASSWORD`) et n'est pas stocké : GLPI n'en a pas besoin.

## Premier démarrage
```bash
cd compose/glpi
mkdir -p data/glpi data/db
sudo chown -R 33:33 data/glpi          # www-data dans le conteneur GLPI
sudo chown -R 999:999 data/db          # mysql dans le conteneur MariaDB
sops secrets.sops.env                  # GLPI_DB_PASSWORD=...
cd ../.. && scripts/compose-up.sh glpi
docker logs -f glpi                    # attendre le logo GLPI (« installation completed »)
```

## Après l'installation (obligatoire)
Comptes créés par défaut : `glpi/glpi` (super-admin), `tech/tech`, `normal/normal`, `post-only/postonly`.
1. Se connecter avec `glpi`, changer son mot de passe (ou créer un admin nominatif et désactiver `glpi`).
2. Changer le mot de passe ou désactiver `tech`, `normal`, `post-only` (GLPI affiche un avertissement tant que ce n'est pas fait).
3. Configuration > Générale : renseigner l'URL publique (celle du reverse proxy).
4. Activer la 2FA pour les comptes administrateurs.

## Reverse proxy
npmplus → `http://<IP du Mini PC>:8090`. Restreindre le port 8090 au reverse proxy dans pfSense (IP dans `private/`).

Le HTTPS est terminé par npmplus : `apache-https.conf` force `HTTPS=on` côté PHP, sinon GLPI génère des redirections en `http://`
(symptôme : après `/ReAuth/Prompt`, alerte du navigateur « informations non sécurisées »).
Dans Configuration > Générale, l'URL de l'application doit être `https://...`.

## Sauvegarde
- Base : `docker exec glpi-db sh -c 'mariadb-dump -uglpi -p"$MARIADB_PASSWORD" --single-transaction glpi' > glpi.sql` (hors Git, `*.sql` ignoré).
- Fichiers : `data/glpi/` (contient `config/glpicrypt.key`, indispensable pour relire les mots de passe chiffrés en base).

## Mise à jour
Changer la version de l'image dans `compose.yaml`, puis `scripts/compose-up.sh glpi pull && scripts/compose-up.sh glpi`.
La mise à jour de la base est automatique au démarrage. Sauvegarder base + `data/glpi` avant.
