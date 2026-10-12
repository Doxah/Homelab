# Modèle de stack

1. Copier ce dossier : `compose/<nom-du-service>/`.
2. Adapter `compose.yaml` : chaque secret est une variable `${NOM:?secret manquant}`.
3. Remplir le fichier de secrets chiffré (s'ouvre dans l'éditeur, chiffré à l'enregistrement) :
   ```bash
   sops compose/<nom-du-service>/secrets.sops.env
   ```
   Le fichier est livré **pré-rempli** avec une ligne commentée par variable (`# VAR=<description>`) :
   décommenter chaque ligne et remplacer la valeur.
4. Donner le dossier de données à l'utilisateur du conteneur : `sudo chown -R 1000:1000 compose/<nom-du-service>/data`.
5. Lancer : `scripts/compose-up.sh <nom-du-service>`.

## Moindre privilège

Le modèle part du cadre le plus strict. Si le conteneur ne démarre pas, lire `docker logs` et relâcher **une seule** option, en commentant pourquoi :

| Symptôme dans les logs | Option à ajuster |
|---|---|
| `Permission denied` / `EACCES` sur `/data` | `chown` du dossier vers l'UID de `user:` |
| `Read-only file system` sur un chemin | ajouter ce chemin dans `tmpfs:` (ou un volume s'il doit persister) |
| `Operation not permitted` | l'image a besoin d'une capacité : `cap_add: [NOM]` (chercher laquelle) |
| L'image refuse de tourner sans root | retirer `user:` et garder `cap_drop` + `cap_add` minimal |
| Conteneur tué (`OOMKilled`) | augmenter `mem_limit` |

Vérifier le résultat :
```bash
docker exec <conteneur> id
docker inspect -f 'user={{.Config.User}} ro={{.HostConfig.ReadonlyRootfs}} capdrop={{.HostConfig.CapDrop}} capadd={{.HostConfig.CapAdd}}' <conteneur>
```
