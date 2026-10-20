#!/usr/bin/env bash
# Déploiement automatique du Mini PC après un push sur main (voir docs/14-deploiement-auto.md).
# Usage :
#   scripts/deploiement-auto.sh --cron    lancé chaque minute par cron : ne fait rien sans demande du webhook
#   scripts/deploiement-auto.sh           à la main : vérifie GitHub tout de suite, même sans demande
#   scripts/deploiement-auto.sh --essai   montre ce qui serait déployé, sans pull ni relance
# Crontab de l'utilisateur qui lance les stacks (pas root) :
#   * * * * * $HOME/Homelab/scripts/deploiement-auto.sh --cron >> $HOME/logs/deploiement-auto.log 2>&1
#
# Étapes : git fetch → refus si modifications locales ou historique réécrit → fast-forward de main
#          → stacks modifiées ∩ compose/deploiement-auto.txt → scripts/compose-up.sh <stack> up -d --remove-orphans
#          → notification ntfy (topic homelab-deploiements) + métrique pour la supervision.
set -euo pipefail

BRANCHE=main
TOPIC=homelab-deploiements

depot="$(cd "$(dirname "$0")/.." && pwd)"
compose="$depot/compose"
declencheur="$compose/webhook/data/declencheur/deploiement"
textfile_dir="$compose/monitoring/data/textfile"

journal() { printf '%s %s\n' "$(date '+%F %T')" "$*"; }

# Notification ntfy : token et domaine déchiffrés à la volée, jamais écrits sur le disque.
# Un échec d'envoi n'interrompt pas le déploiement.
notifier() {
  local titre="$1" message="$2" priorite="${3:-3}" tags="${4:-}" domaine token
  domaine="$(sops decrypt "$compose/commun.sops.env" 2>/dev/null | sed -n 's/^DOMAIN=//p')" || true
  token="$(sops decrypt "$compose/webhook/secrets.sops.env" 2>/dev/null | sed -n 's/^NTFY_TOKEN=//p')" || true
  if [[ -z "$domaine" || -z "$token" ]]; then
    journal "ATTENTION : DOMAIN ou NTFY_TOKEN introuvable, pas de notification"
    return 0
  fi
  curl -fsS -m 10 -o /dev/null \
    -H "Authorization: Bearer $token" -H "Title: $titre" -H "Priority: $priorite" -H "Tags: $tags" \
    --data-binary "$message" "https://ntfy.$domaine/$TOPIC" \
    || journal "ATTENTION : envoi ntfy en échec"
}

# Métrique lue par node_exporter (collecteur textfile de la stack monitoring). 1 = dernier déploiement réussi.
metrique() {
  [[ -d "$textfile_dir" ]] || return 0
  local tmp
  tmp="$(mktemp "$textfile_dir/.deploiement.XXXXXX")"
  cat > "$tmp" <<EOF
# HELP homelab_deploiement_dernier_timestamp_seconds Horodatage Unix du dernier déploiement automatique.
# TYPE homelab_deploiement_dernier_timestamp_seconds gauge
homelab_deploiement_dernier_timestamp_seconds $(date +%s)
# HELP homelab_deploiement_succes 1 si le dernier déploiement automatique a réussi, 0 sinon.
# TYPE homelab_deploiement_succes gauge
homelab_deploiement_succes $1
EOF
  chmod 644 "$tmp"
  mv -f "$tmp" "$textfile_dir/deploiement.prom"
}

echec() {
  journal "ÉCHEC : $1"
  notifier "Déploiement refusé" "$1" 4 rotating_light
  metrique 0
  exit 1
}

main() {
  local mode="${1:-manuel}"
  case "$mode" in --cron|--essai|manuel) ;; *) echo "Usage : $0 [--cron|--essai]" >&2; exit 2 ;; esac

  # Mode cron : sortie immédiate et silencieuse sans demande du webhook (coût quasi nul chaque minute)
  if [[ "$mode" == "--cron" && ! -f "$declencheur" ]]; then exit 0; fi

  # Un seul déploiement à la fois ; un push qui arrive pendant le déploiement sera traité à la minute suivante
  mkdir -p "$HOME/.cache"
  exec 9>"$HOME/.cache/deploiement-auto.lock"
  flock -n 9 || { journal "Déploiement déjà en cours, on passe"; exit 0; }

  # Supprimé AVANT le fetch : une nouvelle demande pendant le déploiement recrée le fichier
  [[ "$mode" == "--essai" ]] || rm -f "$declencheur"

  cd "$depot"
  git fetch --quiet origin "$BRANCHE" || echec "git fetch impossible (réseau, GitHub ?)"

  local avant apres
  avant="$(git rev-parse HEAD)"
  apres="$(git rev-parse "origin/$BRANCHE")"
  if [[ "$avant" == "$apres" ]]; then journal "Déjà à jour ($(git rev-parse --short HEAD))"; exit 0; fi

  [[ "$(git rev-parse --abbrev-ref HEAD)" == "$BRANCHE" ]] || echec "le Mini PC n'est pas sur la branche $BRANCHE"
  # Fichiers suivis modifiés sur le Mini PC : on ne les écrase jamais (les data/ sont ignorés par Git)
  [[ -z "$(git status --porcelain --untracked-files=no)" ]] \
    || echec "modifications locales sur le Mini PC : $(git status --porcelain --untracked-files=no | awk '{print $2}' | paste -sd ' ' -)"
  # Historique réécrit (force push) : un fast-forward est impossible, on laisse la main
  git merge-base --is-ancestor "$avant" "$apres" || echec "historique de $BRANCHE réécrit (force push ?) : à traiter à la main"

  local fichiers
  fichiers="$(git diff --name-only "$avant" "$apres")"

  # Liste blanche lue dans la NOUVELLE version : une stack ajoutée à la liste dans le même commit est prise en compte
  local autorisees
  autorisees=" $(git show "$apres:compose/deploiement-auto.txt" 2>/dev/null | sed 's/#.*//' | tr -s ' \t\r' '\n' | grep -v '^$' | paste -sd ' ' -) "

  # Stacks touchées : compose/<stack>/… hors fichiers .md (la doc seule ne relance rien).
  # compose/commun.sops.env modifié = toutes les stacks de la liste blanche.
  local -a touchees=() a_deployer=() manuelles=()
  local f s
  while IFS= read -r f; do
    [[ -n "$f" ]] || continue
    if [[ "$f" == compose/commun.sops.env ]]; then
      for s in $autorisees; do touchees+=("$s"); done
    elif [[ "$f" =~ ^compose/([^/_][^/]*)/ && "$f" != *.md ]]; then
      touchees+=("${BASH_REMATCH[1]}")
    fi
  done <<< "$fichiers"

  local deja=" "
  for s in "${touchees[@]}"; do
    [[ "$deja" == *" $s "* ]] && continue
    deja+="$s "
    if [[ "$autorisees" == *" $s "* ]]; then a_deployer+=("$s"); else manuelles+=("$s"); fi
  done

  local resume
  resume="$(git log --format='%h %s' "$avant..$apres" | head -5)"
  journal "Nouveaux commits $(git rev-parse --short "$avant")..$(git rev-parse --short "$apres") — à déployer : ${a_deployer[*]:-aucune} — à la main : ${manuelles[*]:-aucune}"

  if [[ "$mode" == "--essai" ]]; then
    printf '%s\n' "$resume"
    exit 0
  fi

  git merge --ff-only --quiet "origin/$BRANCHE" || echec "git merge --ff-only en échec"

  local -a ok=() ko=()
  for s in "${a_deployer[@]}"; do
    if [[ ! -f "$compose/$s/compose.yaml" ]]; then
      # Stack supprimée du dépôt : on ne fait pas de down automatique
      manuelles+=("$s (supprimée : down à la main)")
      continue
    fi
    journal "Relance de $s"
    # Nouvelle version du script : appelé en tant que fichier, il est relu après le merge
    if "$depot/scripts/compose-up.sh" "$s" up -d --remove-orphans; then ok+=("$s"); else ko+=("$s"); fi
  done

  local message
  message="$resume"
  [[ ${#ok[@]} -gt 0 ]] && message+=$'\n'"✅ Relancées : ${ok[*]}"
  [[ ${#ko[@]} -gt 0 ]] && message+=$'\n'"❌ En échec : ${ko[*]} (voir ~/logs/deploiement-auto.log)"
  [[ ${#manuelles[@]} -gt 0 ]] && message+=$'\n'"✋ À relancer à la main : ${manuelles[*]}"
  [[ ${#ok[@]} -eq 0 && ${#ko[@]} -eq 0 && ${#manuelles[@]} -eq 0 ]] && message+=$'\n'"Aucune stack à relancer (doc, scripts…)"

  if [[ ${#ko[@]} -gt 0 ]]; then
    journal "Terminé avec des échecs : ${ko[*]}"
    notifier "Déploiement en échec" "$message" 4 x
    metrique 0
    exit 1
  fi
  journal "Terminé"
  notifier "Déploiement $(git rev-parse --short HEAD)" "$message" 2 rocket
  metrique 1
}

# main appelé en dernière ligne : bash a lu tout le script avant que git merge ne remplace ce fichier
main "$@"
exit
