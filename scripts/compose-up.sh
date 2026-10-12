#!/usr/bin/env bash
# Lance une stack de compose/ en injectant ses secrets SOPS en mémoire (aucun fichier en clair sur le disque).
# Usage : scripts/compose-up.sh <stack> [commande docker compose]
#   scripts/compose-up.sh jellyfin            -> docker compose up -d
#   scripts/compose-up.sh jellyfin pull
#   scripts/compose-up.sh jellyfin config     -> vérifier l'interpolation (affiche les secrets !)
set -euo pipefail

stack="${1:?Usage : $0 <stack> [commande docker compose]}"
shift
[[ $# -eq 0 ]] && set -- up -d

dir="$(cd "$(dirname "$0")/.." && pwd)/compose/$stack"
[[ -f "$dir/compose.yaml" ]] || { echo "Stack introuvable : $dir/compose.yaml" >&2; exit 1; }
cd "$dir"

if [[ -f secrets.sops.env ]]; then
  # Garde-fou CRLF : un \r dans une valeur déchiffrée la rend invalide (ex. « invalid IP address: 127.0.0.1 »).
  # Les valeurs restent dans le pipe, seuls les noms des variables fautives sont affichés.
  fautives="$(sops decrypt secrets.sops.env | grep $'\r' | cut -d= -f1 | tr -d '\r' | paste -sd ' ' -)" || true
  if [[ -n "$fautives" ]]; then
    echo "ERREUR : fins de ligne CRLF dans compose/$stack/secrets.sops.env (variables : $fautives)." >&2
    echo "Corriger : sops edit compose/$stack/secrets.sops.env, cliquer sur CRLF dans la barre d'état de VS Code, choisir LF, enregistrer." >&2
    exit 1
  fi
  exec sops exec-env secrets.sops.env "docker compose $*"
else
  exec docker compose "$@"
fi
