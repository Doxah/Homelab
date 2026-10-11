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
  exec sops exec-env secrets.sops.env "docker compose $*"
else
  exec docker compose "$@"
fi
