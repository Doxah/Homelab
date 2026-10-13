# ConvertX

Conversion de fichiers (documents, images, audio, vidéo) via une interface web.

| | |
|---|---|
| Image | `ghcr.io/c4illin/convertx` |
| Accès | `https://convertx.<DOMAIN>` via Traefik (port 3000 non publié) |
| Données | `./data` (non versionné) |
| Secrets | `secrets.sops.env` : `JWT_SECRET`, `DOMAIN` |

## Lancer
Prérequis : la stack `traefik` tourne (elle crée le réseau `proxy`).
```bash
scripts/compose-up.sh convertx
```

## Régénérer le secret JWT
```bash
sops compose/convertx/secrets.sops.env   # remplacer JWT_SECRET par : openssl rand -hex 32
```
Changer `JWT_SECRET` déconnecte les sessions en cours.
