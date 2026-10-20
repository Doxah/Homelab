#!/usr/bin/env bash
# Hooks de Backrest (stack compose/backrest), appelés par les hooks du dépôt « minipc » (data/config/config.json) :
#   avant  <plan>                                 SNAPSHOT_START (FATAL)         arrête les conteneurs du plan qui tournent
#   apres  <plan>                                 SNAPSHOT_END + SNAPSHOT_ERROR  relance ceux que « avant » a arrêtés
#   succes <plan> <octets_lus> <octets_ajoutes>   SNAPSHOT_SUCCESS               métrique pour la supervision (textfile)
#   erreur <plan> <tache>   (détail sur stdin)    ANY_ERROR + SNAPSHOT_WARNING   notification ntfy
#
# Pas besoin de SOPS pour relancer : « docker start » redémarre le conteneur EXISTANT, avec l'environnement
# (secrets compris) injecté à sa création par scripts/compose-up.sh. Rien n'est recréé.
#
# Environnement (compose.yaml) : DOCKER_API, NTFY_URL, NTFY_TOKEN, TEXTFILE_DIR, ETAT_DIR
# Test à la main : docker exec backrest bash /hooks/backrest-hook.sh avant vaultwarden   (puis « apres »)
set -uo pipefail

# Conteneurs à arrêter par plan, dans l'ordre d'arrêt (relance dans l'ordre inverse).
# Un plan absent de la liste n'arrête rien (ex. « hote »).
# ⚠ Toute modification doit être reportée dans -allowPOST de socket-proxy-backrest (compose.yaml) : sinon HTTP 403.
declare -A CONTENEURS=(
  [vaultwarden]="vaultwarden"
  [jellyfin]="seerr radarr sonarr jackett transmission jellyfin"   # gluetun reste en marche (port forwardé)
  [soulsync]="soulsync slskd"
  [arcane]="arcane"
  [discopanel]="discopanel"      # en s'arrêtant, DiscoPanel arrête proprement les serveurs Minecraft (monde enregistré)
  [infra]="grafana"
)

# Délai d'arrêt propre avant SIGKILL, en secondes
DELAI_DEFAUT=60
declare -A DELAI=(
  [discopanel]=150               # le temps d'arrêter les serveurs Minecraft
)

DOCKER_API="${DOCKER_API:-http://socket-proxy-backrest:2375}"
ETAT_DIR="${ETAT_DIR:-/data/etat-hooks}"
TEXTFILE_DIR="${TEXTFILE_DIR:-/textfile}"

journal() { printf '%s [%s] %s\n' "$(date '+%F %T')" "${plan:-?}" "$*"; }

# Notification ntfy : titre, priorité, tags ; message sur stdin. Un échec d'envoi ne fait jamais échouer le hook.
notifier() {
  if [[ -z "${NTFY_URL:-}" || -z "${NTFY_TOKEN:-}" ]]; then
    journal "ATTENTION : NTFY_URL ou NTFY_TOKEN absent, pas de notification"
    cat > /dev/null
    return 0
  fi
  curl -fsS -m 15 -o /dev/null \
    -H "Authorization: Bearer $NTFY_TOKEN" -H "Title: $1" -H "Priority: $2" -H "Tags: $3" \
    --data-binary @- "$NTFY_URL" \
    || journal "ATTENTION : envoi ntfy en échec"
}

# Appel de l'API Docker (via le socket-proxy) : méthode, chemin, délai max. Affiche le code HTTP (000 = injoignable).
docker_api() {
  curl -sS -o /dev/null -w '%{http_code}' -m "$3" -X "$1" "$DOCKER_API$2" 2>/dev/null || true
}

relancer() {
  local etat="$ETAT_DIR/$plan.arretes" c code i
  local -a liste=() echecs=()
  if [[ ! -s "$etat" ]]; then
    rm -f "$etat"
    journal "rien à relancer"
    return 0
  fi
  mapfile -t liste < "$etat"
  for (( i=${#liste[@]}-1; i>=0; i-- )); do
    c="${liste[i]}"
    [[ -n "$c" ]] || continue
    code="$(docker_api POST "/containers/$c/start" 60)"
    case "$code" in
      204) journal "relancé : $c" ;;
      304) journal "déjà démarré : $c" ;;
      *)   journal "ERREUR : relance de $c impossible (HTTP $code)"; echecs+=("$c") ;;
    esac
  done
  if (( ${#echecs[@]} )); then
    printf '%s\n' "${echecs[@]}" > "$etat"        # conservé : le prochain « avant » ou « apres » réessaiera
    printf 'Conteneur(s) toujours arrêté(s) après la sauvegarde %s : %s\nÀ relancer : docker start %s\n' \
      "$plan" "${echecs[*]}" "${echecs[*]}" \
      | notifier "Sauvegarde $plan : relance en échec" 5 rotating_light
    return 1
  fi
  rm -f "$etat"
}

arreter() {
  local liste="${CONTENEURS[$plan]-}" etat="$ETAT_DIR/$plan.arretes" c code delai
  if [[ -z "$liste" ]]; then
    journal "aucun conteneur à arrêter pour ce plan"
    return 0
  fi
  mkdir -p "$ETAT_DIR"
  # Reste d'une sauvegarde interrompue (Backrest redémarré pendant l'arrêt) : relancer d'abord
  if [[ -s "$etat" ]]; then
    journal "conteneurs restés arrêtés lors d'un passage précédent : relance d'abord"
    relancer || true
  fi
  : > "$etat"
  for c in $liste; do
    delai="${DELAI[$c]:-$DELAI_DEFAUT}"
    code="$(docker_api POST "/containers/$c/stop?t=$delai" $((delai + 30)))"
    case "$code" in
      204) echo "$c" >> "$etat"; journal "arrêté : $c" ;;
      304) journal "déjà arrêté : $c (ne sera pas relancé)" ;;
      404) journal "absent : $c (stack non déployée ?), ignoré" ;;
      *)   journal "ERREUR : arrêt de $c impossible (HTTP $code ; 403 = nom absent de -allowPOST du socket-proxy)"
           relancer || true                       # ne jamais laisser une stack à moitié arrêtée
           return 1 ;;
    esac
  done
}

# Métrique lue par node_exporter (collecteur textfile de la stack monitoring), écrite seulement après un snapshot RÉUSSI :
# un échec ne met rien à jour et l'alerte SauvegardeEnRetard part au-delà de 26 h.
# Même HELP que scripts/vaultwarden-backup.sh pour la métrique commune (node_exporter refuse des HELP différents).
metrique() {
  local lus="${1:-0}" ajoutes="${2:-0}" tmp
  [[ "$lus" =~ ^[0-9]+$ ]] || lus=0
  [[ "$ajoutes" =~ ^[0-9]+$ ]] || ajoutes=0
  if [[ ! -d "$TEXTFILE_DIR" ]]; then
    journal "dossier $TEXTFILE_DIR absent (stack monitoring ?), pas de métrique"
    return 0
  fi
  tmp="$(mktemp "$TEXTFILE_DIR/.backrest-$plan.XXXXXX")" || return 1
  cat > "$tmp" <<EOF
# HELP homelab_sauvegarde_derniere_reussite_timestamp_seconds Horodatage Unix de la dernière sauvegarde réussie.
# TYPE homelab_sauvegarde_derniere_reussite_timestamp_seconds gauge
homelab_sauvegarde_derniere_reussite_timestamp_seconds{tache="$plan",outil="backrest"} $(date +%s)
# HELP homelab_sauvegarde_donnees_lues_octets Volume de données parcouru par la dernière sauvegarde réussie.
# TYPE homelab_sauvegarde_donnees_lues_octets gauge
homelab_sauvegarde_donnees_lues_octets{tache="$plan",outil="backrest"} $lus
# HELP homelab_sauvegarde_donnees_ajoutees_octets Données nouvelles envoyées au dépôt par la dernière sauvegarde réussie.
# TYPE homelab_sauvegarde_donnees_ajoutees_octets gauge
homelab_sauvegarde_donnees_ajoutees_octets{tache="$plan",outil="backrest"} $ajoutes
EOF
  chmod 644 "$tmp"                                   # node_exporter tourne en nobody
  mv -f "$tmp" "$TEXTFILE_DIR/backrest-$plan.prom"   # renommage atomique
  journal "métrique écrite : backrest-$plan.prom"
}

erreur() {
  local tache="${1:-?}" detail
  detail="$(head -c 3000)"
  printf 'Tâche : %s\n%s\n' "$tache" "${detail:-(pas de détail)}" \
    | notifier "Sauvegarde ${plan:-dépôt} : problème" 4 "warning,floppy_disk"
}

action="${1:-}"
plan="${2:-}"
if [[ ! "$plan" =~ ^[A-Za-z0-9_-]*$ ]]; then
  echo "Identifiant de plan invalide : $plan" >&2
  exit 2
fi

case "$action" in
  avant)  arreter ;;
  apres)  relancer ;;
  succes) metrique "${3:-0}" "${4:-0}" ;;
  erreur) erreur "${3:-?}" ;;
  *)      echo "Usage : $0 avant|apres|succes|erreur <plan> [...]" >&2; exit 2 ;;
esac
