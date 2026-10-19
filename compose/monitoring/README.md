# Supervision (Mini PC)

Métriques, journaux, alertes et tableaux de bord du homelab, en Docker sur le Mini PC, derrière Traefik.
Les mêmes outils (Prometheus, Alertmanager, Grafana, Loki) seront repris sur K3s avec `kube-prometheus-stack` (partie 2 de la feuille de route).

```
                    ┌──────────────── Mini PC (stack monitoring) ────────────────┐
node_exporter ──────┤                                                            │
cAdvisor ───────────┤                                                            │
Traefik, cloudflared, ntfy ─► Prometheus ──► règles (prometheus/regles) ──► Alertmanager ──► ntfy ──► téléphone
snmp-exporter ◄─ SNMPv3 ─ NAS ×3, switch      │                                             │
blackbox ◄─ HTTPS ─ services publiés          ├──► Grafana ◄── Loki ◄── Alloy ◄── journaux Docker
pfSense (node_exporter) ──────────────────────┘
```

## Composants
| Conteneur | Rôle | Publié |
|---|---|---|
| `prometheus` | Collecte et stocke les métriques (30 jours, 10 Go max), évalue les règles d'alerte | `prometheus.<domaine>` (lan-admin) |
| `alertmanager` | Regroupe les alertes et les envoie à ntfy (`homelab-alertes`) | `alertmanager.<domaine>` (lan-admin) |
| `grafana` | Tableaux de bord (dossier *Homelab*) et exploration des journaux | `grafana.<domaine>` (lan-admin) |
| `loki` | Stocke les journaux (30 jours) | non |
| `alloy` | Lit les journaux de tous les conteneurs et les envoie à Loki | non |
| `node-exporter` | CPU, RAM, disques, réseau, températures du Mini PC + fichiers `.prom` des scripts | `BIND_IP:9100` (réseau de l'hôte) |
| `cadvisor` | CPU, RAM, réseau, redémarrages par conteneur | non |
| `snmp-exporter` | Traduit le SNMP des NAS et du switch | non |
| `blackbox-exporter` | Sondes HTTPS : service joignable + expiration du certificat | non |
| `socket-proxy-mon` | API Docker en lecture seule pour Alloy et cAdvisor | non (réseau `socket` interne) |

Notifications : stack séparée [`compose/ntfy`](../ntfy/README.md), à lancer **avant** celle-ci.

## Choix
| Sujet | Choix | Pourquoi |
|---|---|---|
| IP et domaine | Modèles `${VAR}` dans `prometheus/cibles/*.yml` et `alertmanager/alertmanager.yml`, rendus au démarrage par `rendre-modeles.sh` dans un tmpfs | Prometheus et Alertmanager ne lisent pas les variables d'environnement. Les valeurs restent dans SOPS, rien en clair sur le disque. (Les `configs:`/`secrets:` de Compose ne marchent pas avec `read_only: true`) |
| Notifications | Alertmanager → ntfy auto-hébergé, modèle `alertmanager` intégré à ntfy | Priorité *urgent* pour `severity=critique`, *default* sinon ; message aussi à la résolution |
| pfSense | Paquet `node_exporter` | Plus riche que le SNMP de pfSense (bsnmpd, v2c seulement) et mêmes tableaux de bord que le Mini PC |
| NAS, switch | SNMPv3 *authPriv* (SHA + AES), un compte en lecture seule | Le v2c envoie la communauté en clair ; seuls les identifiants v3 peuvent venir de l'environnement dans snmp_exporter |
| Journaux | Loki + Alloy, journaux Docker par l'API | Pas d'accès aux fichiers de `/var/lib/docker/containers`, pas de root pour Alloy |
| Tableaux de bord | Provisionnés depuis `grafana/dashboards/` | Versionnés dans Git ; *Node Exporter Full* (rfmoz), *Traefik officiel*, *Homelab — vue d'ensemble* |

### Exceptions au moindre privilège (documentées)
- **node-exporter** : `network_mode: host` et `pid: host`, sinon il ne voit que l'interface et les processus du conteneur.
  Compensé par : utilisateur `nobody`, aucune capacité, `/` monté en lecture seule, écoute sur `BIND_IP` uniquement.
- **cadvisor** : tourne en **root** (lecture de `/var/lib/docker`, propriété de root en 710). Compensé par : aucune capacité,
  pas `privileged`, système de fichiers et montages en lecture seule, API Docker via `socket-proxy-mon` (GET seulement).
- **prometheus**, **alertmanager** : `entrypoint` remplacé par `sh rendre-modeles.sh …` (busybox de l'image), puis `exec` du binaire habituel.

## Secrets (`secrets.sops.env`, chiffré)
Livré **pré-rempli** avec une ligne commentée par variable : `sops compose/monitoring/secrets.sops.env`, décommenter, remplacer.
`DOMAIN` et `BIND_IP` viennent de `compose/commun.sops.env` : ne pas les redéfinir.

| Variable | Rôle |
|---|---|
| `GRAFANA_ADMIN_USER`, `GRAFANA_ADMIN_PASSWORD` | Compte admin Grafana. **Lu au premier démarrage seulement** : ensuite, changer le mot de passe avec `docker exec -it grafana grafana cli admin reset-admin-password` |
| `NTFY_TOKEN_ALERTMANAGER` | Token du compte `alertmanager` de ntfy (le même que dans `compose/ntfy/secrets.sops.env`) |
| `DOCKER_GID` | `getent group docker \| cut -d: -f3` |
| `PFSENSE_IP` | IP de pfSense côté DATACENTER (là où écoute node_exporter) |
| `SWITCH_IP`, `SYNO_IP`, `QNAP_TS259_IP`, `QNAP_TS228_IP` | IP d'administration des équipements SNMP |
| `SNMP_V3_USER`, `SNMP_V3_AUTH_PASSWORD`, `SNMP_V3_PRIV_PASSWORD` | Compte SNMPv3 en lecture seule, identique sur les NAS et le switch (8 caractères minimum par mot de passe) |

Une variable manquante arrête le conteneur concerné avec `ERREUR : variable X absente (modèle …)` (Prometheus, Alertmanager)
ou `secret manquant` (Compose). Un NAS retiré : commenter ses lignes dans `prometheus/cibles/snmp-qnap.yml`.

## Préparer les équipements (une fois)
### pfSense : node_exporter
1. *System › Package Manager › Available Packages* : installer **node_exporter**.
2. *Services › node_exporter* : activer, interface d'écoute = **DATACENTER** uniquement (jamais WAN), port 9100.
   Collecteurs : seulement ceux marqués `(*)` (+ `devstat`, `ntp`). `buddyinfo`, `runit`, `supervisord` sont propres à Linux :
   cochés, le service ne démarre pas, sans message dans l'interface. Après *Save*, le démarrer dans *Status › Services*.
3. Règle pare-feu sur DATACENTER : source Mini PC → *This firewall* TCP 9100 (avec les règles proposées dans `private/regles-pfsense-proposees.md`).
4. Test depuis le Mini PC : `curl -s http://<PFSENSE_IP>:9100/metrics | head`.

### Synology DS216J : SNMPv3
*Panneau de configuration › Terminal & SNMP › SNMP* : cocher **SNMPv3**, utilisateur = `SNMP_V3_USER`,
protocole **SHA** + mot de passe, confidentialité **AES** + mot de passe. Décocher SNMPv1/v2c.

### QNAP TS-259 Pro+ et TS-228 : SNMPv3
*Panneau de configuration › Réseau et services de fichiers › SNMP* : activer, version **SNMPv3**, même utilisateur,
authentification **HMAC-SHA**, confidentialité **CBC-DES** ou **AES** selon ce que propose le firmware.
Si seul DES est disponible : ajouter `__param_auth: homelab_v3_des` sous `labels:` de ce NAS dans `prometheus/cibles/snmp-qnap.yml`.

### Switch D-Link DGS-1210-24P : SNMPv3
*Management › SNMP Settings* : activer SNMP, créer une vue en lecture (OID `1`), un groupe v3 *AuthPriv* lié à cette vue en lecture,
puis l'utilisateur v3 (SHA + AES/DES). Désactiver les communautés `public`/`private` par défaut. DES seulement → même
astuce `__param_auth: homelab_v3_des` dans `prometheus/cibles/snmp-switch.yml`.

### Pare-feu
**ufw sur le Mini PC** (politique `deny incoming`) : node_exporter écoute sur l'hôte, pas dans un conteneur, donc Prometheus
passe par la chaîne INPUT et il faut l'autoriser. L'interface du réseau de la stack a un nom fixe (`br-monitoring`) :
```bash
sudo ufw allow in on br-monitoring to any port 9100 proto tcp comment 'Prometheus -> node_exporter'
```

Depuis le Mini PC : UDP 161 vers les NAS (VLAN NAS) et le switch, TCP 9100 vers pfSense. Aujourd'hui tout passe (règles `pass any`),
à reprendre avec l'étape proxy.8 / base.6.

Test SNMP sans installer d'outil, une fois la stack lancée :
```bash
docker exec prometheus wget -qO- 'http://snmp-exporter:9116/snmp?target=<IP>&auth=homelab_v3&module=system' | head
```

## Premier démarrage
```bash
cd ~/Homelab/compose/monitoring
# Dossiers de données AVANT le 1er lancement (create_host_path: false : sinon échec explicite), en 1000:1000
mkdir -p data/{prometheus,alertmanager,grafana,loki,alloy,textfile}
chmod 755 data/textfile                         # lu par node-exporter (nobody)
ls -ln data                                     # tout en 1000:1000

cd ~/Homelab
scripts/compose-up.sh monitoring config --quiet # valide l'interpolation sans afficher les secrets
scripts/compose-up.sh ntfy monitoring           # ntfy d'abord
scripts/compose-up.sh monitoring ps             # prometheus, alertmanager, grafana : healthy
```
Puis dans le navigateur (depuis le LAN admin ou le VPN) :
1. `https://prometheus.<domaine>/targets` : toutes les cibles **UP** (le DS216J peut mettre jusqu'à 50 s).
2. `https://prometheus.<domaine>/rules` : les groupes de règles chargés, aucune en erreur.
3. `https://grafana.<domaine>` : dossier **Homelab** › *Homelab — vue d'ensemble*.
4. Grafana › *Explore* › Loki : `{container="traefik"} | json` affiche les journaux d'accès.

### Tester la chaîne d'alerte
```bash
docker exec alertmanager amtool alert add alertname=TestHomelab severity=avertissement nom=test \
  --annotation='summary="Test de la chaine d alerte"' --alertmanager.url=http://localhost:9093
```
La notification arrive sur `homelab-alertes` dans les 30 s, puis « résolue » au bout de 5 min environ.

## Modifier
| Pour… | Faire |
|---|---|
| Ajouter un service à sonder | Ligne dans `prometheus/cibles/https.yml` (seulement les services sans lan-admin), puis `scripts/compose-up.sh monitoring restart prometheus` |
| Ajouter un équipement SNMP | Variable dans `secrets.sops.env` + `environment:` de prometheus + ligne dans `prometheus/cibles/snmp-*.yml`, puis `scripts/compose-up.sh monitoring up -d` |
| Modifier une règle ou `prometheus.yml` | Éditer puis `docker exec prometheus wget -qO- --post-data= http://localhost:9090/-/reload` |
| Modifier un tableau de bord | L'éditer dans Grafana (non enregistrable), *Exporter › JSON*, remplacer le fichier dans `grafana/dashboards/`, committer |
| Couper une alerte prévue (maintenance, arrêt volontaire) | `https://alertmanager.<domaine>` › *New Silence* |
| Superviser une sauvegarde | À la fin du script, écrire `homelab_sauvegarde_derniere_reussite_timestamp_seconds{tache="<nom>"} <date +%s>` dans `data/textfile/<nom>.prom` (voir `scripts/vaultwarden-backup.sh`) |

## Alertes
| Fichier | Alertes |
|---|---|
| `regles/hotes.yml` | Cible injoignable, disque > 85 % / > 95 % / plein dans 24 h, RAM < 10 %, CPU > 90 %, température > 85 °C, redémarrage |
| `regles/conteneurs.yml` | Conteneur disparu, redémarrages en boucle, mémoire > 90 % du `mem_limit` |
| `regles/services.yml` | Sonde HTTPS en échec, certificat < 14 j / < 5 j, Traefik > 20 % de 5xx, tunnel Cloudflare coupé |
| `regles/nas.yml` | Panne système/alimentation, RAID dégradé ou pas revenu à la normale, disque en échec ou > 50 °C, volume > 90 % |
| `regles/sauvegardes.yml` | Sauvegarde réussie il y a plus de 26 h, ou jamais vue |
| `regles/supervision.yml` | Notifications en échec, règle en erreur, collecte SNMP trop lente |

`severity: critique` → priorité *urgent* sur le téléphone, rappel toutes les 4 h ; `avertissement` → priorité normale, rappel toutes les 12 h.
Les métriques Synology détaillées (RAID, disques, températures) n'existent que pour le DS216J ; pour les QNAP, seuls l'espace des volumes,
la RAM et le réseau sont suivis (la MIB QNAP n'est pas dans le `snmp.yml` de l'image).

## Dépannage
| Symptôme | Cause probable |
|---|---|
| `permission denied` sur `/prometheus`, `/loki`, `/var/lib/grafana` | Dossier `data/…` absent ou en root : `ls -ln data`, recréer en 1000:1000 |
| Prometheus redémarre avec `ERREUR : variable … absente` | Secret manquant ou vide dans `secrets.sops.env` |
| Cible `mini-pc` (9100) `context deadline exceeded`, mais `curl` OK depuis l'hôte | Règle ufw `br-monitoring` absente (voir Pare-feu) |
| Cible `pfsense` (9100) en timeout, aucun blocage dans les journaux | node_exporter arrêté sur pfSense : *Diagnostics › Command Prompt* `sockstat -4l \| grep 9100` ; retirer les collecteurs Linux et démarrer le service |
| Cible SNMP `context deadline exceeded` | Pare-feu UDP 161, SNMPv3 non activé, ou mauvais protocole de chiffrement (essayer `homelab_v3_des`) |
| Cible SNMP `wrong digest` / `unknown user name` | Utilisateur ou mot de passe SNMPv3 différent sur l'équipement |
| `cadvisor` : `permission denied` sur `/var/lib/docker/...` | Ajouter `cap_add: [DAC_READ_SEARCH]` au service et le noter ici |
| Pas de journaux dans Loki | `docker logs alloy` ; `docker logs socket-proxy-mon` montre-t-il des requêtes bloquées ? |
| Les sondes HTTPS échouent toutes | Résolution DNS des `*.<domaine>` depuis les conteneurs (pfSense host overrides) ou Traefik arrêté |
| `CibleInjoignable` sur `cloudflared` | La stack `compose/cloudflared` n'est pas encore lancée (étape proxy.9) : la lancer, ou commenter son job dans `prometheus.yml` |

## Suite
- Surveillance de la supervision : un *dead man's switch* (alerte toujours active envoyée à healthchecks.io) préviendrait si le Mini PC entier tombe — ntfy tombe avec lui.
- Journaux système de l'hôte (journald) dans Loki : demande le groupe `systemd-journal` pour Alloy.
- Santé des disques QNAP : générer un module SNMP à partir de la MIB QNAP (`snmp_exporter` *generator*).
