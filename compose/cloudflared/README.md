# cloudflared (Mini PC)

Un seul tunnel Cloudflare pour tout le homelab. Il remplace les deux conteneurs lancés à la main
(`docker run cloudflare/cloudflared`, un pour Jellyfin, un pour le site), qui ne redémarraient pas après un reboot.

```
Internet → Cloudflare → cloudflared (réseau proxy) → Traefik :8443 → videos / demande-videos / immich / site…
```

| | |
|---|---|
| Type de tunnel | géré depuis Cloudflare (token), routes dans le dashboard Zero Trust |
| Secrets | `secrets.sops.env` : `TUNNEL_TOKEN` |
| Ports publiés | aucun (connexion sortante uniquement) |
| Moindre privilège | 65532 (nonroot), `cap_drop: ALL`, lecture seule, pas de socket Docker |

## Règle pour chaque nom public
Zero Trust → Networks → Tunnels → *homelab* → Public Hostname → Add :

| Champ | Valeur |
|---|---|
| Subdomain / Domain | ex. `videos` / `<DOMAIN>` |
| Service | `HTTPS` — `traefik:8443` |
| Additional settings → TLS → **Origin Server Name** | le nom public complet, ex. `videos.<DOMAIN>` |

Sans *Origin Server Name*, cloudflared présente le SNI `traefik`, que Traefik refuse (`sniStrict`).
Ne publier **que** des services prévus pour Internet. Les routers `lan-admin` refusent de toute façon le trafic du tunnel.

## Bascule depuis les anciens tunnels
1. Créer le tunnel : Zero Trust → Networks → Tunnels → Create → *Cloudflared*, nom `homelab`.
   Copier le token (la chaîne après `--token` dans la commande proposée), puis sur le PC :
   `sops compose/cloudflared/secrets.sops.env` → décommenter `TUNNEL_TOKEN=`.
2. Sur le Mini PC : `git pull && scripts/compose-up.sh cloudflared`, puis `docker ps --filter name=cloudflared`
   doit afficher `(healthy)` et le tunnel apparaître *Healthy* dans le dashboard.
3. Pour chaque nom public, l'un après l'autre (coupure de quelques secondes) :
   supprimer le Public Hostname dans l'**ancien** tunnel (le CNAME DNS part avec), puis l'ajouter au tunnel `homelab`
   avec la règle ci-dessus. Tester depuis l'extérieur (4G).
   - `videos`, `demande-videos` : routers Traefik déjà en place.
   - Le site / portfolio : ajouter d'abord les labels Traefik + le réseau `proxy` dans son compose (son dépôt, redéployé par Arcane).
4. Quand l'ancien tunnel n'a plus de nom : `docker rm -f <ancien conteneur>`, puis supprimer l'ancien tunnel dans le dashboard.
5. Retirer les ports devenus inutiles : `8096` (Jellyfin) et `5055` (Seerr) dans `compose/jellyfin/compose.yaml`,
   puis `scripts/compose-up.sh jellyfin`. Les clients TV qui utilisaient `IP:8096` passent sur `https://videos.<DOMAIN>`.

## Vérifier
```bash
docker logs --tail 20 cloudflared        # « Registered tunnel connection » ×4
curl -sI https://videos.<DOMAIN>  # depuis l'extérieur
```

## Plus tard
- Routes du tunnel en code avec le provider Terraform `cloudflare/cloudflare` (objectif tf).
- IP réelle des visiteurs dans Jellyfin : déclarer le réseau `proxy` dans *Known proxies* de Jellyfin et faire confiance
  aux en-têtes `X-Forwarded-For` de cloudflared dans Traefik (`forwardedHeaders.trustedIPs`).
