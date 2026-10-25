#!/usr/bin/env bash
# Exécute sur l'hôte les demandes d'action de l'agent de dépannage (compose/agent, voir docs/15-agent-depannage.md).
#
# L'agent (conteneur sans socket Docker en écriture ni clé SOPS) ne peut que DÉPOSER une demande :
#   compose/agent/data/actions/demandes/<id>.demande   (id=…, stack=…, action=restart|up, service=…, raison=…)
# Ce script la valide puis lance scripts/compose-up.sh, et écrit la réponse que l'agent attend :
#   compose/agent/data/actions/resultats/<id>.resultat (code=…, puis la fin de la sortie de docker compose)
#
# Garde-fous (indépendants de l'agent : une demande forgée est refusée de la même façon) :
#   - stack et action dans compose/agent-actions.txt (lu dans le dépôt du Mini PC, donc la version de main) ;
#   - noms vérifiés par expressions régulières, aucune valeur passée à un shell ;
#   - au plus MAX_PAR_HEURE actions par stack et par heure ;
#   - attend la fin d'un déploiement automatique en cours (même verrou que scripts/deploiement-auto.sh).
#
# Usage :
#   scripts/agent-actions.sh --cron     chaque minute par cron : traite les demandes pendant ~1 min (toutes les 5 s)
#   scripts/agent-actions.sh            à la main : traite une fois les demandes en attente
# Crontab de l'utilisateur qui lance les stacks (pas root) :
#   * * * * * $HOME/Homelab/scripts/agent-actions.sh --cron >> $HOME/logs/agent-actions.log 2>&1
set -euo pipefail

MAX_PAR_HEURE=3
DUREE_MAX_S=300                                   # une commande docker compose bloquée ne bloque pas tout

depot="$(cd "$(dirname "$0")/.." && pwd)"
dossier="$depot/compose/agent/data/actions"
liste="$depot/compose/agent-actions.txt"
cache="$HOME/.cache/agent-actions"

journal() { printf '%s %s\n' "$(date '+%F %T')" "$*"; }

# Réponse lue par l'outil « action » de l'agent (écriture atomique : il ne lit jamais un fichier à moitié écrit)
repondre() {
  local id="$1" code="$2" texte="$3" tmp
  tmp="$(mktemp "$dossier/resultats/.$id.XXXXXX")"
  printf 'code=%s\nfin=%s\n---\n%s\n' "$code" "$(date '+%F %T')" "$texte" > "$tmp"
  chmod 644 "$tmp"
  mv -f "$tmp" "$dossier/resultats/$id.resultat"
}

# Règle de la liste blanche pour une stack : « restart up !gluetun » (vide = stack absente)
regle_de() {
  sed 's/#.*//' "$liste" 2>/dev/null | awk -F: -v s="$1" '{ gsub(/[ \t\r]+$/, "", $1) } $1 == s { $1 = ""; print; exit }'
}

traiter() {
  local fichier="$1" nom id="" stack="" action="" service="" raison="" cle valeur
  nom="$(basename "$fichier" .demande)"

  # Lecture stricte : clés connues uniquement, rien n'est évalué
  while IFS='=' read -r cle valeur; do
    case "$cle" in
      id) id="$valeur" ;; stack) stack="$valeur" ;; action) action="$valeur" ;;
      service) service="$valeur" ;; raison) raison="${valeur//[[:cntrl:]]/ }" ;;
    esac
  done < <(head -c 2048 "$fichier")
  rm -f "$fichier"

  if [[ ! "$nom" =~ ^[A-Za-z0-9_-]{1,100}$ || "$id" != "$nom" ]]; then
    journal "REFUS : demande mal formée ($nom)"
    [[ "$nom" =~ ^[A-Za-z0-9_-]{1,100}$ ]] && repondre "$nom" 2 "REFUS : demande mal formée"
    return 0
  fi
  local refus=""
  [[ "$stack" =~ ^[a-z0-9][a-z0-9_-]{0,40}$ && -f "$depot/compose/$stack/compose.yaml" ]] || refus="stack inconnue « $stack »"
  [[ -z "$refus" && ! "$action" =~ ^(restart|up)$ ]] && refus="action inconnue « $action »"
  [[ -z "$refus" && -n "$service" && ! "$service" =~ ^[a-z0-9][a-z0-9_.-]{0,60}$ ]] && refus="service invalide"

  local regle
  if [[ -z "$refus" ]]; then
    regle=" $(regle_de "$stack") "
    if [[ "$regle" == "  " ]]; then refus="stack « $stack » absente de compose/agent-actions.txt"
    elif [[ "$regle" != *" $action "* ]]; then refus="« $action » non autorisé sur « $stack »"
    elif [[ "$regle" == *" !"* && -z "$service" ]]; then refus="« $stack » a des services exclus : préciser le service"
    elif [[ -n "$service" && "$regle" == *" !$service "* ]]; then refus="service « $service » exclu des actions automatiques"
    fi
  fi

  # Limite de fréquence par stack (horodatages de la dernière heure)
  local maintenant compte=0
  maintenant="$(date +%s)"
  if [[ -z "$refus" ]]; then
    mkdir -p "$cache"
    touch "$cache/$stack"
    awk -v limite=$((maintenant - 3600)) '$1 > limite' "$cache/$stack" > "$cache/$stack.tmp"
    mv -f "$cache/$stack.tmp" "$cache/$stack"
    compte="$(wc -l < "$cache/$stack")"
    (( compte >= MAX_PAR_HEURE )) && refus="déjà $compte actions sur « $stack » dans l'heure (max $MAX_PAR_HEURE)"
  fi

  if [[ -n "$refus" ]]; then
    journal "REFUS $id : $refus"
    repondre "$id" 2 "REFUS : $refus"
    return 0
  fi

  echo "$maintenant" >> "$cache/$stack"
  local -a cmd=("$depot/scripts/compose-up.sh" "$stack" --)
  if [[ "$action" == restart ]]; then cmd+=(restart); else cmd+=(up -d); fi
  [[ -n "$service" ]] && cmd+=("$service")
  journal "ACTION $id : $action $stack ${service:-(stack)} — raison : $raison"

  # Pas pendant un déploiement automatique (même verrou que deploiement-auto.sh), 2 min d'attente au plus
  exec 8>"$HOME/.cache/deploiement-auto.lock"
  if ! flock -w 120 8; then
    exec 8>&-
    journal "REFUS $id : déploiement automatique en cours"
    repondre "$id" 3 "REFUS : déploiement automatique en cours depuis plus de 2 minutes, réessayer plus tard"
    return 0
  fi
  local sortie code=0
  sortie="$(timeout "$DUREE_MAX_S" "${cmd[@]}" 2>&1)" || code=$?
  exec 8>&-
  journal "RÉSULTAT $id : code $code"
  repondre "$id" "$code" "$(printf '%s\n' "$sortie" | tail -n 40)"
}

main() {
  local mode="${1:-manuel}" passes=1 i f
  case "$mode" in --cron) passes=12 ;; manuel) ;; *) echo "Usage : $0 [--cron]" >&2; exit 2 ;; esac

  [[ -d "$dossier/demandes" ]] || exit 0          # stack agent pas installée
  mkdir -p "$dossier/resultats" "$HOME/.cache"
  exec 9>"$HOME/.cache/agent-actions.lock"
  flock -n 9 || exit 0                            # une passe précédente tourne encore

  for ((i = 1; i <= passes; i++)); do
    for f in "$dossier"/demandes/*.demande; do
      [[ -f "$f" ]] && traiter "$f"
    done
    # Nettoyage : résultats de plus de 7 jours
    find "$dossier/resultats" -name '*.resultat' -mtime +7 -delete 2>/dev/null || true
    (( i < passes )) && sleep 5
  done
}

main "$@"
