# Arcane

Interface web de gestion Docker. Synchronise aussi le portfolio depuis son dépôt Git (GitOps en mode pull).

| | |
|---|---|
| Image | `ghcr.io/getarcaneapp/manager` |
| Accès | `https://arcane.<DOMAIN>` via Traefik, postes d'admin uniquement (`lan-admin@docker`) |
| Données | volume `arcane_arcane-data` |
| Secrets | `secrets.sops.env` : `ENCRYPTION_KEY` ; `DOMAIN` dans `compose/commun.sops.env` |

## Exception au moindre privilège
Arcane a accès au socket Docker : c'est un accès root sur l'hôte tant que Docker n'est pas en mode rootless.
Conséquences :
- l'interface ne doit **jamais** être exposée sur Internet, et sur le réseau local seulement au poste d'admin et au reverse proxy ;
- protéger le compte Arcane par un mot de passe fort (et l'OIDC/2FA si disponible) ;
- la vraie correction est Docker rootless (objectif « moindre privilège », étapes 9 et 10).

## Lancer
```bash
scripts/compose-up.sh arcane
```
