# DiscoPanel (Mini PC)

Panel des serveurs Minecraft. Crée lui-même les conteneurs des serveurs via le socket Docker (exception documentée
au moindre privilège, voir `compose.yaml`).

| | |
|---|---|
| Accès | `https://disco.<DOMAIN>` via Traefik, postes d'admin uniquement (`lan-admin@docker`) |
| Ports publiés | 25565/tcp, 25565-25665/udp (Minecraft), sur `BIND_IP` uniquement |
| Moindre privilège | socket Docker (exception documentée), root sans capacités sauf `CHOWN DAC_OVERRIDE FOWNER`, `no-new-privileges`, 512 Mo / 1 CPU |
| Données | `DISCOPANEL_HOST_DATA_PATH` (serveurs), `./backups`, `./tmp` — jamais dans Git |
| Secrets | `secrets.sops.env` : `DISCOPANEL_HOST_DATA_PATH` ; `DOMAIN` dans `compose/commun.sops.env` |

## Migration vers ce dossier (une seule fois)
```bash
docker inspect -f '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{println}}{{end}}' discopanel   # relever le chemin de /app/data
sops compose/discopanel/secrets.sops.env      # renseigner DISCOPANEL_HOST_DATA_PATH avec ce chemin (sur le PC)
cd <ancien dossier> && docker compose down
mv backups tmp ~/Homelab/compose/discopanel/ 2>/dev/null
cd ~/Homelab && scripts/compose-up.sh discopanel config --quiet && scripts/compose-up.sh discopanel
```
Les conteneurs des serveurs Minecraft ne sont pas touchés : ils sont gérés par DiscoPanel, pas par ce compose.
