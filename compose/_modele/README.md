# Modèle de stack

1. Copier ce dossier : `compose/<nom-du-service>/`.
2. Adapter `compose.yaml` : chaque secret est une variable `${NOM:?secret manquant}`.
3. Créer le fichier de secrets chiffré (s'ouvre dans l'éditeur, chiffré à l'enregistrement) :
   ```bash
   sops compose/<nom-du-service>/secrets.sops.env
   ```
   Contenu au format `.env` :
   ```
   DB_PASSWORD=...
   API_TOKEN=...
   ```
4. Lancer : `scripts/compose-up.sh <nom-du-service>`.

Les valeurs non secrètes (ports, chemins, fuseau horaire) restent en clair dans `compose.yaml`.
