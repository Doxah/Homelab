#!/usr/bin/env bash
# Lance une ou plusieurs stacks de compose/ en injectant leurs secrets SOPS en mémoire (aucun fichier en clair sur le disque).
# Usage : scripts/compose-up.sh <stack> [<stack>...] [commande docker compose]
#   scripts/compose-up.sh jellyfin                  -> docker compose up -d
#   scripts/compose-up.sh jellyfin soulsync down    -> down sur les deux stacks (ordre inverse)
#   scripts/compose-up.sh jellyfin pull
#   scripts/compose-up.sh jellyfin config           -> vérifier l'interpolation (affiche les secrets !)
#   scripts/compose-up.sh jellyfin -- logs -f       -> « -- » force la fin de la liste des stacks
# Les premiers arguments qui correspondent à un dossier compose/<nom>/compose.yaml sont des stacks,
# le reste est la commande docker compose. Autocomplétion : source scripts/compose-up.completion.bash
set -euo pipefail

racine="$(cd "$(dirname "$0")/.." && pwd)/compose"

stacks=()
while [[ $# -gt 0 ]]; do
  if [[ "$1" == "--" ]]; then shift; break; fi
  [[ -f "$racine/$1/compose.yaml" ]] || break
  stacks+=("$1"); shift
done

if [[ ${#stacks[@]} -eq 0 ]]; then
  echo "Usage : $0 <stack> [<stack>...] [commande docker compose]" >&2
  [[ $# -gt 0 ]] && echo "Stack introuvable : $racine/$1/compose.yaml" >&2
  echo "Stacks disponibles : $(cd "$racine" && for d in */; do [[ -f "$d/compose.yaml" && "$d" != _* ]] && printf '%s ' "${d%/}"; done)" >&2
  exit 1
fi
[[ $# -eq 0 ]] && set -- up -d

# down/stop : ordre inverse (ex. traefik arrêté en dernier s'il est listé en premier).
if [[ "$1" == "down" || "$1" == "stop" ]]; then
  inverse=(); for ((i=${#stacks[@]}-1; i>=0; i--)); do inverse+=("${stacks[i]}"); done
  stacks=("${inverse[@]}")
fi

# Variables communes à toutes les stacks (DOMAIN, BIND_IP…) : compose/commun.sops.env, déchiffrées une seule fois
# et exportées avant celles de la stack. Une variable définie dans le secrets.sops.env de la stack est prioritaire.
commun="$racine/commun.sops.env"
if [[ -f "$commun" ]]; then
  communs="$(sops decrypt "$commun")"                                  # échec de déchiffrement = arrêt (set -e)
  while IFS= read -r ligne; do
    [[ "$ligne" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]] || continue     # ignore commentaires et lignes vides
    valeur="${BASH_REMATCH[2]}"
    if [[ "$valeur" == *$'\r'* ]]; then
      echo "ERREUR : fin de ligne CRLF dans compose/commun.sops.env (variable : ${BASH_REMATCH[1]})." >&2
      exit 1
    fi
    export "${BASH_REMATCH[1]}=$valeur"
  done <<< "$communs"
  unset communs
fi

# Une stack = un sous-shell : le cd et les secrets de la stack ne fuient pas vers la suivante.
lancer_stack() (
  stack="$1"; shift
  cd "$racine/$stack"
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
)

echecs=()
for stack in "${stacks[@]}"; do
  [[ ${#stacks[@]} -gt 1 ]] && echo "==> $stack : docker compose $*"
  lancer_stack "$stack" "$@" || echecs+=("$stack")   # une stack en échec n'empêche pas les suivantes
done

if [[ ${#echecs[@]} -gt 0 ]]; then
  echo "ÉCHEC : ${echecs[*]}" >&2
  exit 1
fi
