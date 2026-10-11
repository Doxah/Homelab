# ConvertX

Conversion de fichiers (documents, images, audio, vidéo) via une interface web.

| | |
|---|---|
| Image | `ghcr.io/c4illin/convertx` |
| Port | 3000 |
| Données | `./data` (non versionné) |
| Secrets | `secrets.sops.env` : `JWT_SECRET` |

## Lancer
```bash
scripts/compose-up.sh convertx
```

## Régénérer le secret JWT
```bash
sops compose/convertx/secrets.sops.env   # remplacer JWT_SECRET par : openssl rand -hex 32
```
Changer `JWT_SECRET` déconnecte les sessions en cours.
