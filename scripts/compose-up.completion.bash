# Autocomplétion bash pour scripts/compose-up.sh
# Installation : ajouter dans ~/.bashrc :
#   source /chemin/vers/homelab/scripts/compose-up.completion.bash
# Propose les stacks de compose/ (dossiers avec compose.yaml, hors _modele), puis les commandes docker compose.

_compose_up() {
  local cur="${COMP_WORDS[COMP_CWORD]}" script racine i mot
  script="${COMP_WORDS[0]/#\~/$HOME}"
  racine="$(cd "$(dirname "$script")/.." 2>/dev/null && pwd)/compose"
  [[ -d "$racine" ]] || return 0

  local stacks=() d
  for d in "$racine"/*/; do
    d="${d%/}"; d="${d##*/}"
    [[ "$d" == _* || ! -f "$racine/$d/compose.yaml" ]] && continue
    stacks+=("$d")
  done

  # Tant que tous les mots précédents sont des stacks, on propose des stacks (non encore saisies) + les commandes.
  local deja=" " en_stacks=1
  for ((i=1; i<COMP_CWORD; i++)); do
    mot="${COMP_WORDS[i]}"
    if [[ $en_stacks -eq 1 && -f "$racine/$mot/compose.yaml" ]]; then deja+="$mot "; else en_stacks=0; fi
  done

  local commandes="up down pull restart stop start logs ps config exec"
  if [[ $en_stacks -eq 1 ]]; then
    local restants=() s
    for s in "${stacks[@]}"; do [[ "$deja" == *" $s "* ]] || restants+=("$s"); done
    # Pas de stack saisie : uniquement les stacks
    if [[ $COMP_CWORD -eq 1 ]]; then
      COMPREPLY=($(compgen -W "${restants[*]}" -- "$cur"))
    else
      COMPREPLY=($(compgen -W "${restants[*]} $commandes" -- "$cur"))
    fi
  elif [[ $COMP_CWORD -ge 2 && " up " == *" ${COMP_WORDS[COMP_CWORD-1]} "* ]]; then
    COMPREPLY=($(compgen -W "-d --build --force-recreate --remove-orphans" -- "$cur"))
  fi
}
# Enregistré aussi pour les chemins relatifs : bash cherche d'abord une complétion pour le chemin tapé tel quel,
# et bash-completion y colle sinon une complétion « fichiers » par défaut (_comp_complete_minimal).
_compose_up_abs="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/compose-up.sh"
complete -F _compose_up compose-up.sh ./scripts/compose-up.sh scripts/compose-up.sh ./compose-up.sh "$_compose_up_abs"
unset _compose_up_abs
