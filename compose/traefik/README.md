# Traefik (Mini PC)

Reverse proxy du Mini PC. Remplace **npmplus** (CT LXC sur le T130) : la configuration vit dans Git
(labels des compose + `dynamic/*.yml`) au lieu d'une base SQLite modifiée à la main dans une interface web.
C'est aussi l'ingress par défaut de K3s : les notions (entrypoints, routers, middlewares, certresolvers) resserviront.

```
Postes LAN ──► pfSense (host overrides *.DOMAIN → Mini PC) ──► Traefik :443 ──► réseau Docker « proxy » ──► conteneurs
                                                                   │
                                                                   ├──► dynamic/externes.yml (copie de .exemple) ──► T130, NAS… (hors Docker)
                                                                   └──► socket-proxy (lecture seule) ──► /var/run/docker.sock
```

## Choix
| Sujet | Choix | Pourquoi |
|---|---|---|
| Découverte des services | Labels Docker + provider file | Chaque stack déclare son propre routage ; le hors-Docker passe par `dynamic/` |
| Socket Docker | [wollomatic/socket-proxy](https://github.com/wollomatic/socket-proxy) | `docker.sock` = root sur l'hôte. Le proxy n'autorise que des `GET` (conteneurs, événements, version), uniquement depuis le conteneur `traefik`, sur un réseau `internal` |
| Certificats | Wildcard `*.DOMAIN` en DNS-01 Cloudflare | Aucun port à ouvrir, vrais certificats aussi pour les services internes (Vaultwarden) |
| Ports | 80/443 publiés sur `BIND_IP`, 8000/8443 dans le conteneur | Traefik tourne en 1000:1000 sans aucune capacité |
| Tableau de bord | `traefik.DOMAIN`, middleware `lan-admin@docker` (défini par label sur Traefik, `ADMIN_CIDRS`) | Jamais en mode `insecure`, jamais publié en direct |

## Secrets (`secrets.sops.env`, chiffré)
Livré **pré-rempli** avec une ligne commentée par variable : `sops compose/traefik/secrets.sops.env`, décommenter, remplacer.

| Variable | Rôle |
|---|---|
| `DOMAIN` | Domaine racine (certificat `DOMAIN` + `*.DOMAIN`, routers) |
| `BIND_IP` | IP LAN du Mini PC (80/443 publiés uniquement dessus) |
| `ACME_EMAIL` | Compte Let's Encrypt |
| `CF_DNS_API_TOKEN` | Token Cloudflare **dédié** (https://dash.cloudflare.com/profile/api-tokens → *Create Token* → modèle *Edit zone DNS*) avec 2 permissions : **Zone › DNS › Edit** + **Zone › Zone › Read**, ressources = la zone du domaine. Jamais la Global API Key |
| `ADMIN_CIDRS` | Réseaux autorisés sur les interfaces d'admin, séparés par des virgules (ex. le LAN de ton PC) |
| `DOCKER_GID` | GID du groupe `docker` du Mini PC : `getent group docker \| cut -d: -f3` |

## Premier démarrage
```bash
cd compose/traefik
mkdir -p data && touch data/acme.json && chmod 600 data/acme.json   # AVANT le 1er lancement : sinon Docker crée ./data en root
ls -ln data                                  # dossier ET acme.json en 1000:1000 (sinon : « open /data/acme.json: permission denied »)
ss -tlnp | grep -E ':(80|443) '                                      # rien ne doit déjà écouter sur 80/443

cd ../.. && scripts/compose-up.sh traefik config --quiet && scripts/compose-up.sh traefik pull && scripts/compose-up.sh traefik
docker logs -f traefik      # attendre « Register... » puis l'obtention du certificat (DNS-01 : 1 à 2 min)
docker ps --filter name=traefik --filter name=socket-proxy    # les deux en (healthy)
```
Conseil : pour le tout premier essai, décommenter la ligne `caserver` (staging Let's Encrypt) dans `compose.yaml`,
puis la recommenter, vider `data/acme.json` et relancer une fois que tout fonctionne.

Test sans toucher au DNS, depuis ton PC :
```bash
curl -vk --resolve traefik.<DOMAIN>:443:<BIND_IP> https://traefik.<DOMAIN>/dashboard/
```

## Publier un service
Dans le `compose.yaml` de la stack :
```yaml
services:
  app:
    # plus besoin de `ports:` : Traefik joint le conteneur par le réseau proxy
    networks: [default, proxy]
    labels:
      traefik.enable: "true"
      traefik.http.routers.app.rule: Host(`app.${DOMAIN:?secret manquant}`)
      traefik.http.services.app.loadbalancer.server.port: "8080"
      # interface d'admin : ajouter
      # traefik.http.routers.app.middlewares: lan-admin@docker

networks:
  proxy:
    external: true
```
- `DOMAIN` (et `BIND_IP`) viennent de `compose/commun.sops.env`, chargé par `scripts/compose-up.sh` pour toutes les stacks.
  Une valeur redéfinie dans le `secrets.sops.env` d'une stack est prioritaire.
- Websockets : rien à faire (pris en charge nativement, contrairement à la case à cocher de npmplus).
- Une base de données ne rejoint **jamais** le réseau `proxy`.

## Migration depuis npmplus
Faire service par service, npmplus reste en place tant que tout n'est pas passé :
1. Lancer Traefik (ci-dessus) et vérifier le certificat wildcard.
2. Pour un service : ajouter les labels + le réseau `proxy`, retirer son `ports:`, relancer la stack.
3. Tester avec `curl --resolve` (sans toucher au DNS).
4. Dans pfSense (*Services → DNS Resolver → Host Overrides*), faire pointer le sous-domaine vers le Mini PC au lieu de npmplus.
5. Supprimer l'hôte dans npmplus. Les services restés sur le T130 ou les NAS passent par `dynamic/externes.yml` (copier `externes.yml.exemple`, ne jamais laisser un fichier vide ou `http: {}`).
6. Quand npmplus n'a plus d'hôte : arrêter le CT, le supprimer après 1-2 semaines.

**Vaultwarden** : terminer d'abord sa bascule avec npmplus (une seule chose à la fois), puis le passer derrière Traefik
en HTTP sur le réseau `proxy` : retirer `ROCKET_TLS`, le port publié et le dossier `tls/` (le chiffrement est assuré par Traefik).
Ajouter `lan-admin@docker` sur un router dédié à `PathPrefix(`/admin`)`.

**Pare-feu** : autoriser les postes LAN vers le Mini PC en 80/443, puis retirer les règles vers les ports
publiés directement (8443, 8008…) au fur et à mesure.

**Tunnels Cloudflare (plus tard)** : un seul `cloudflared` sur le réseau `proxy`, ingress vers `https://traefik:8443`
avec `originServerName` = le sous-domaine, au lieu d'un cloudflared par service.

## Moindre privilège
```bash
for c in traefik socket-proxy; do docker exec $c id 2>/dev/null; docker inspect -f '{{.Name}} user={{.Config.User}} ro={{.HostConfig.ReadonlyRootfs}} capdrop={{.HostConfig.CapDrop}}' $c; done
# Le socket-proxy doit refuser tout ce qui n'est pas un GET autorisé :
docker logs socket-proxy | grep -i "blocked" | tail
```
Si Traefik ne voit aucun conteneur : `docker logs socket-proxy` (requête bloquée = chemin à ajouter dans `-allowGET`,
lancer temporairement en `-loglevel=debug` pour voir lequel).

## Sauvegarde
`data/acme.json` (certificats + clé du compte ACME). Perte sans gravité : Traefik redemande un certificat au démarrage.
Tout le reste est dans Git.

## Mise à jour
Changer les tags d'image, puis `scripts/compose-up.sh traefik pull && scripts/compose-up.sh traefik`.
Lire les notes de version de Traefik avant un changement de version mineure (options renommées).
