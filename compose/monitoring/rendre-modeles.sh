#!/bin/sh
# Rend des fichiers modèles puis lance le programme du conteneur (utilisé comme entrypoint par Prometheus et Alertmanager).
# Usage : sh rendre-modeles.sh <dossier des modèles> <dossier de sortie> -- <commande> [arguments...]
#
# Chaque ${VAR} est remplacé par la variable d'environnement VAR (injectée par scripts/compose-up.sh depuis les secrets SOPS).
# Variable absente ou vide = arrêt avec un message clair, comme ${VAR:?} dans Compose. Les lignes de commentaire (#) sont
# recopiées telles quelles : une cible commentée peut garder sa variable sans qu'elle soit définie.
# Le dossier de sortie est un tmpfs : les valeurs rendues (IP, token) ne sont jamais écrites sur le disque.
# Fonctionne avec la busybox des images prom/* (sh + awk), aucun outil à installer.
set -eu

src="$1"; dst="$2"; shift 2
[ "${1:-}" = "--" ] && shift
[ $# -gt 0 ] || { echo "rendre-modeles.sh : commande à lancer manquante" >&2; exit 1; }

mkdir -p "$dst"
for f in "$src"/*; do
  [ -f "$f" ] || continue
  case "$f" in *.exemple|*.md) continue ;; esac
  awk -v fichier="$f" '
    /^[[:space:]]*#/ { print; next }
    {
      reste = $0; sortie = ""
      while (match(reste, /\$\{[A-Za-z_][A-Za-z0-9_]*\}/)) {
        nom = substr(reste, RSTART + 2, RLENGTH - 3)
        if (!(nom in ENVIRON) || ENVIRON[nom] == "") {
          printf "ERREUR : variable %s absente (modèle %s, ligne %d)\n", nom, fichier, NR > "/dev/stderr"
          erreur = 1; exit 1
        }
        sortie = sortie substr(reste, 1, RSTART - 1) ENVIRON[nom]   # valeur jamais ré-analysée
        reste = substr(reste, RSTART + RLENGTH)
      }
      print sortie reste
    }
    END { if (erreur) exit 1 }
  ' "$f" > "$dst/$(basename "$f")"
done

exec "$@"
