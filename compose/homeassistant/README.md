# Home Assistant

Domotique : automatisations, tableaux de bord, intégration des appareils connectés.

| | |
|---|---|
| Image | `ghcr.io/home-assistant/home-assistant` (version figée dans `compose.yaml`) |
| Accès | `https://ha.<DOMAIN>` via Traefik, limité à `ADMIN_CIDRS` (postes d'admin + VPN) ; port 8123 non publié |
| Configuration | `configuration.yaml` (versionné, monté en lecture seule) |
| Données | `./data` (base SQLite, `.storage`, sauvegardes HA), non versionné |
| Secrets | `secrets.sops.env` : `HA_TRUSTED_PROXY_CIDR` ; `DOMAIN` vient de `compose/commun.sops.env` |

## Premier lancement
Prérequis : la stack `traefik` tourne (elle crée le réseau `proxy`).

1. Relever le sous-réseau du réseau `proxy` et le saisir dans les secrets (ligne pré-remplie à décommenter) :
   ```bash
   docker network inspect proxy -f '{{range .IPAM.Config}}{{.Subnet}}{{end}}'
   sops compose/homeassistant/secrets.sops.env
   ```
2. Créer le dossier de données avec les trois fichiers que l'interface écrit (sans eux, `!include` échoue) :
   ```bash
   cd compose/homeassistant
   mkdir data
   for f in automations scripts scenes; do echo "[]" > data/$f.yaml; done
   cd ../..
   ```
3. Lancer et suivre le premier démarrage (2 à 3 minutes) :
   ```bash
   scripts/compose-up.sh homeassistant
   docker logs -f homeassistant
   ```
4. Ouvrir `https://ha.<DOMAIN>` et créer le compte propriétaire (assistant d'accueil). Nom, position, unités et fuseau se règlent à cette étape : ils sont stockés dans `data/.storage`, pas dans `configuration.yaml`.

## Pourquoi `configuration.yaml` est en lecture seule
La configuration vit dans Git comme le reste du homelab : on la modifie dans le dépôt, on pousse, on relance la stack. L'éditeur YAML de l'interface ne peut donc pas la modifier. Les automatisations, scripts et scènes créés dans l'interface restent, eux, dans `data/` (donc dans les sauvegardes, pas dans Git).

## Moindre privilège
L'image officielle démarre sous s6-overlay en **root** et ne gère pas `user:`. Le reste du cadre strict est appliqué : `cap_drop: [ALL]` avec la seule capacité `DAC_OVERRIDE`, `no-new-privileges`, système de fichiers en lecture seule, ressources plafonnées. **Cette combinaison n'a pas été testée** : si le conteneur ne démarre pas, relâcher **une seule** option à la fois, dans cet ordre :

| Symptôme dans les logs | Option à ajuster |
|---|---|
| `Read-only file system` sur un chemin | ajouter ce chemin dans `tmpfs:` ; en dernier recours `read_only: false` |
| `Operation not permitted` (chown, setuid) | `cap_add` : `CHOWN`, `FOWNER`, `SETUID`, `SETGID` |
| Ping ou découverte DHCP en échec | `cap_add: [NET_RAW]` |
| `Permission denied` sur `/config` | vérifier que `data/` appartient à `administrateur` |
| Conteneur tué (`OOMKilled`) | augmenter `mem_limit` |

## Accès via Traefik : erreur 400
Sans `use_x_forwarded_for` et sans le bon sous-réseau dans `trusted_proxies`, Home Assistant répond **400 Bad Request** derrière un proxy. Si le sous-réseau du réseau `proxy` change (réseau recréé), mettre à jour `HA_TRUSTED_PROXY_CIDR` puis relancer la stack.

## Accès hors du LAN
Le middleware `lan-admin` limite l'accès aux postes d'admin et au VPN : l'application mobile ne fonctionne donc hors de chez soi que **via le VPN**. Aucune route Cloudflare n'est créée : Home Assistant n'est pas exposé sur Internet. Pour ouvrir à tout le LAN, retirer le label `middlewares`.

Conséquence pour la supervision : ne pas ajouter `ha.<DOMAIN>` aux sondes HTTPS (blackbox) tant que `lan-admin` est actif, il répond 403 depuis le réseau Docker.

## Découverte automatique des appareils (mode host)
En réseau `bridge`, Home Assistant ne reçoit pas les annonces mDNS/SSDP : les appareils se déclarent à la main par IP (MQTT, Hue, Shelly, ESPHome, Zigbee par clé USB… fonctionnent très bien ainsi). Si la découverte devient indispensable, passer en `network_mode: host` : retirer `networks`, `labels` et `ports`, puis déclarer la route côté Traefik, comme pour Transmission, dans `compose/traefik/dynamic/homeassistant.yml` :

```yaml
http:
  routers:
    homeassistant:
      rule: 'Host(`ha.{{ env "DOMAIN" }}`)'
      entryPoints: [websecure]
      middlewares: [lan-admin@docker]
      service: homeassistant
  services:
    homeassistant:
      loadBalancer:
        servers:
          - url: 'http://{{ env "BIND_IP" }}:8123'
```
Le conteneur écoute alors sur toutes les interfaces du Mini PC (pare-feu à prévoir) et `HA_TRUSTED_PROXY_CIDR` devient le sous-réseau d'où Traefik se connecte. Si les appareils sont dans le VLAN IoT, le Mini PC doit y avoir une interface ou un relais mDNS.

## Mise à jour
1. Lire la section « Backward-incompatible changes » des notes de version de la nouvelle version.
2. Lancer une sauvegarde (Backrest, ou `Paramètres > Système > Sauvegardes` dans Home Assistant) : la base est migrée au démarrage, pas de retour arrière.
3. Changer le tag dans `compose.yaml`, puis `scripts/compose-up.sh homeassistant pull` et `scripts/compose-up.sh homeassistant`.

## Sauvegardes
`./data` contient tout ce qui compte (base `home-assistant_v2.db`, `.storage`, automatisations). À ajouter au plan Backrest (conteneur arrêté pendant la sauvegarde). Pour alléger, `recorder: purge_keep_days` dans `configuration.yaml` réduit la taille de la base (10 jours par défaut).
