#!/usr/bin/env bash
# Sauvegarde à chaud de Vaultwarden (Mini PC) : base SQLite cohérente + rsa_key.pem, puis copie vers le NAS.
# Usage : scripts/vaultwarden-backup.sh            (crontab de l'utilisateur qui lance la stack, pas root)
# Prérequis : sqlite3 et rsync sur l'hôte (installés une fois par un compte sudoer).
# Variables (compose/vaultwarden/secrets.sops.env) :
#   BACKUP_DIR        dossier local des archives            (défaut : ~/backups/vaultwarden)
#   BACKUP_KEEP_DAYS  rétention locale en jours             (défaut : 14)
#   RSYNC_DEST        cible rsync, ex. syno-backup:/volume1/<partage>/vaultwarden (rsync via SSH, hôte défini dans ~/.ssh/config)
#                     vide = pas de copie distante
set -euo pipefail

stack_dir="$(cd "$(dirname "$0")/.." && pwd)/compose/vaultwarden"

# Relance sous sops exec-env pour charger les secrets en mémoire
if [[ -z "${_VW_BACKUP_SECRETS:-}" ]]; then
  export _VW_BACKUP_SECRETS=1
  exec sops exec-env "$stack_dir/secrets.sops.env" "$(printf '%q' "$0")"
fi

for c in sqlite3 tar; do command -v "$c" >/dev/null || { echo "ERREUR : $c absent de l'hôte" >&2; exit 1; }; done

data="$stack_dir/data"
dest="${BACKUP_DIR:-$HOME/backups/vaultwarden}"
keep="${BACKUP_KEEP_DAYS:-14}"
stamp="$(date +%Y%m%d-%H%M%S)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
umask 077
mkdir -p "$dest"

# .backup passe par l'API SQLite : inclut le contenu du WAL, sans arrêter le service
sqlite3 "$data/db.sqlite3" ".timeout 10000" ".backup '$work/db.sqlite3'"
[[ "$(sqlite3 "$work/db.sqlite3" 'PRAGMA integrity_check;')" == "ok" ]] || { echo "ERREUR : integrity_check en échec" >&2; exit 1; }
cp -p "$data"/rsa_key*.pem "$work/"
for d in attachments sends; do
  if [[ -d "$data/$d" ]]; then cp -rp "$data/$d" "$work/"; fi
done
if [[ -f "$data/config.json" ]]; then cp -p "$data/config.json" "$work/"; fi

archive="$dest/vaultwarden-$stamp.tar.gz"
tar czf "$archive" -C "$work" .
echo "Sauvegarde locale : $archive ($(du -h "$archive" | cut -f1))"

find "$dest" -name 'vaultwarden-*.tar.gz' -mtime +"$keep" -delete

if [[ -n "${RSYNC_DEST:-}" ]]; then
  command -v rsync >/dev/null || { echo "ERREUR : rsync absent de l'hôte" >&2; exit 1; }
  # Le NAS garde sa propre rétention : pas de --delete
  rsync -a --no-perms --no-owner --no-group "$archive" "$RSYNC_DEST/"
  echo "Copie envoyée vers le NAS"
fi
