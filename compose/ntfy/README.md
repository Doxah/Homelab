# ntfy (Mini PC)

Serveur de notifications push du homelab : reçoit les alertes d'Alertmanager (stack `monitoring`) et les messages
des scripts (sauvegardes…), et les pousse sur le téléphone via l'appli ntfy (Android / iOS).

```
Alertmanager ──► http://ntfy:8080/homelab-alertes ──┐
scripts      ──► https://ntfy.<domaine>/homelab-…  ──┼──► ntfy ──► appli ntfy (téléphone, navigateur)
                                                      │
Internet ──► Cloudflare (tunnel) ──► Traefik ─────────┘   (abonnement depuis l'extérieur)
```

## Choix
| Sujet | Choix | Pourquoi |
|---|---|---|
| Hébergement | Auto-hébergé, derrière Traefik | Les alertes ne sortent pas du homelab (sauf l'option iPhone, voir plus bas) |
| Accès | `auth-default-access: deny-all` | Sans compte, impossible de lire ou d'écrire un topic |
| Comptes | Déclaratifs (`NTFY_AUTH_USERS`, `NTFY_AUTH_TOKENS`, `NTFY_AUTH_ACCESS`) | Recréés à chaque démarrage depuis Git + SOPS : rien à refaire à la main après une réinstallation |
| Topics | `homelab-alertes` (Alertmanager), `homelab-sauvegardes` (scripts) | Préfixe `homelab-` : un seul droit `scripts:homelab-*:wo` |

## Présentation des alertes
Modèle [`modeles/homelab-alertes.yml`](modeles/homelab-alertes.yml), monté dans `/etc/ntfy/templates` et appelé par Alertmanager
avec `?template=homelab-alertes` :
```
🔴 Synology DS216J                                   ← pastille (🔴 critique, 🟠 avertissement, ✅ résolu) + appareil
Critique · en cours                                  ← statut
▸ Le volume Volume 1 est dégradé ou planté (code 11) ← résumé de l'alerte
Un disque est probablement mort : le remplacer…      ← description
Depuis le 20/10 à 10:12                              ← à la résolution : « Du … au … · durée »
```
- Appareil = label `nom` de la cible, traduit en nom lisible par le dictionnaire `$noms` du modèle ; à défaut le conteneur
  (`name`), l'hôte de la sonde HTTPS, puis le job. Un nouvel équipement : ajouter sa paire `"nom" "Nom lisible"` dans `$noms`.
- Priorité calculée par le modèle : 5 (urgente) si critique, 3 si avertissement, 2 à la résolution.
- Le résumé des règles ne répète donc plus l'appareil (`prometheus/regles/*.yml`).
- Après une modification du modèle : `scripts/compose-up.sh ntfy up -d --force-recreate`, puis une fausse alerte
  qui traverse toute la chaîne (résolue automatiquement au bout de 5 min) :
  ```bash
  docker exec alertmanager amtool alert add alertname=TestHomelab severity=critique nom=ds216j \
    --annotation='summary="Test du modele de notification"' --alertmanager.url=http://localhost:9093
  ```
  Un modèle invalide fait répondre ntfy en 400 : `NotificationsEnEchec` se déclenche et `docker logs ntfy` donne la ligne fautive.

## Comptes
| Compte | Rôle | Droits | Utilisé par |
|---|---|---|---|
| `eliot` (au choix) | `admin` | tout | appli du téléphone, interface web |
| `alertmanager` | `user` | écriture seule sur `homelab-alertes` | Alertmanager (token) |
| `scripts` | `user` | écriture seule sur `homelab-*` | scripts de sauvegarde (token) |

## Secrets (`secrets.sops.env`, chiffré)
Livré **pré-rempli** avec une ligne commentée par variable : `sops compose/ntfy/secrets.sops.env`, décommenter, remplacer.
Pas de guillemets autour des valeurs.

| Variable | Contenu |
|---|---|
| `NTFY_AUTH_USERS` | `eliot:<hash>:admin,alertmanager:<hash>:user,scripts:<hash>:user` (séparés par des virgules) |
| `NTFY_AUTH_TOKENS` | `alertmanager:<token>:Alertmanager,scripts:<token>:Scripts` |

Générer les valeurs sur le Mini PC (rien n'est écrit sur le disque) :
```bash
docker run --rm -it binwiederhier/ntfy:v2.32.0 user hash        # demande un mot de passe, affiche le hash bcrypt ($2a$10$…)
docker run --rm binwiederhier/ntfy:v2.32.0 token generate        # affiche un token tk_… (32 caractères)
```
- Un hash par compte. Les mots de passe de `alertmanager` et `scripts` ne servent jamais (ils utilisent leur token) :
  générer un mot de passe long et ne pas le garder.
- Le token `alertmanager` est **aussi** à mettre dans `compose/monitoring/secrets.sops.env` (`NTFY_TOKEN_ALERTMANAGER`).
- Dans le fichier SOPS, les `$` du hash s'écrivent tels quels (pas de `$$` : la valeur arrive par une variable, Compose ne la réinterprète pas).

## Premier démarrage
```bash
cd ~/Homelab/compose/ntfy
mkdir -p data && ls -ln .                       # data en 1000:1000
cd ~/Homelab && scripts/compose-up.sh ntfy
scripts/compose-up.sh ntfy ps                   # healthy
docker exec ntfy ntfy user list                 # les 3 comptes et leurs droits
```

## Test
```bash
# Depuis le Mini PC, avec le token « scripts »
curl -H "Authorization: Bearer tk_…" -d "Test depuis le Mini PC" https://ntfy.<domaine>/homelab-sauvegardes
# Sans token : doit répondre 403 (deny-all)
curl -d "test" https://ntfy.<domaine>/homelab-sauvegardes
```

## Téléphone
1. Appli **ntfy** (F-Droid / Play Store / App Store) → Réglages → *Serveur par défaut* : `https://ntfy.<domaine>`.
2. Réglages → *Gérer les utilisateurs* → ajouter `eliot` + mot de passe pour ce serveur.
3. S'abonner à `homelab-alertes` et `homelab-sauvegardes`.

**Hors de la maison** : deux possibilités.
- **Tunnel Cloudflare** (recommandé pour les notifications) : dans Zero Trust › Tunnels › *Public Hostnames*,
  ajouter `ntfy.<domaine>` → `https://traefik:8443`, *Origin Server Name* = `ntfy.<domaine>` (comme les autres noms).
  Exposé sur Internet, mais tout est refusé sans compte. Ne pas mettre ce nom derrière Cloudflare Access : l'appli ne sait pas s'y authentifier.
- **VPN** : rien d'exposé, mais pas de notification quand le VPN est coupé.

**iPhone** : iOS ne laisse pas l'appli écouter en arrière-plan. Décommenter `NTFY_UPSTREAM_BASE_URL` : le serveur envoie
seulement un identifiant de message à ntfy.sh, qui réveille l'appli ; le contenu reste chez toi. Inutile sur Android.

## Dépannage
| Symptôme | Cause probable |
|---|---|
| `403 forbidden` avec le bon token | Topic hors des droits (`alertmanager` ne peut écrire que sur `homelab-alertes`) |
| Compte absent de `ntfy user list` | Format de `NTFY_AUTH_USERS` (virgules, `:role` final) ; voir `scripts/compose-up.sh ntfy -- logs` |
| `open /var/lib/ntfy/cache.db: permission denied` | `./data` créé par Docker en root : `sudo chown 1000:1000 data` |
