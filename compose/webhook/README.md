# webhook (Mini PC)

Récepteur du webhook GitHub : un push sur `main` déclenche le déploiement automatique du Mini PC.
Fonctionnement complet, installation et dépannage : [docs/14-deploiement-auto.md](../../docs/14-deploiement-auto.md).

| | |
|---|---|
| Image | `almir/webhook` ([adnanh/webhook](https://github.com/adnanh/webhook)) |
| Accès | `https://deploiement.<domaine>/hooks/homelab`, public via le tunnel Cloudflare (seul ce chemin est routé) |
| Secrets | `secrets.sops.env` : `WEBHOOK_SECRET`, `NTFY_TOKEN` (lu par le script hôte) ; `DOMAIN` dans `compose/commun.sops.env` |
| Données | `./data/declencheur/` (un seul fichier, `deploiement`) |
| Moindre privilège | 1000:1000, `cap_drop: ALL`, lecture seule, **pas de socket Docker, pas de dépôt, pas de clé SOPS** |

## Lancer
```bash
mkdir -p compose/webhook/data/declencheur
scripts/compose-up.sh webhook
```
