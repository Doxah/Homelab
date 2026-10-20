# 14 — Déploiement automatique (push GitHub → Mini PC)

Un push sur `main` met à jour `~/Homelab` sur le Mini PC et relance les stacks modifiées autorisées.

```
git push ──► GitHub ──webhook──► Cloudflare (tunnel) ──► Traefik ──► conteneur webhook
                                                                    │ vérifie HMAC + push + main
                                                                    ▼
                                                  compose/webhook/data/declencheur/deploiement
                                                                    │ (cron, chaque minute)
                                                                    ▼
                         scripts/deploiement-auto.sh : git fetch → fast-forward → compose-up.sh <stacks> → ntfy
```

## Pourquoi en deux morceaux
Le conteneur exposé sur Internet ne sait faire **qu'une chose** : poser un fichier. Il n'a ni socket Docker, ni dépôt, ni clé SOPS.
Le déploiement est fait par l'utilisateur `administrateur` sur l'hôte, qui va lui-même chercher le code sur GitHub :
une requête forgée (même avec un secret volé) ne peut pas injecter de code, au pire provoquer un `git fetch` inutile.
Délai entre le push et le déploiement : moins d'une minute.

## Règles du script
| Cas | Comportement |
|---|---|
| Fichier `.md` seul modifié | Rien n'est relancé (le dépôt est quand même mis à jour) |
| `compose/<stack>/…` modifié, stack dans [`compose/deploiement-auto.txt`](../compose/deploiement-auto.txt) | `scripts/compose-up.sh <stack> up -d --remove-orphans` |
| Stack modifiée **hors** liste blanche | Pas relancée, signalée « à relancer à la main » dans la notification |
| `compose/commun.sops.env` modifié | Toutes les stacks de la liste blanche sont relancées |
| Stack supprimée du dépôt | Pas de `down` automatique, signalée |
| Fichier suivi modifié sur le Mini PC | **Refus**, notification : rien n'est écrasé |
| Historique réécrit (force push) | **Refus** (fast-forward impossible), à traiter à la main |
| Deux pushs rapprochés | Un seul déploiement à la fois (`flock`), le second suit à la minute suivante |

Notifications : topic ntfy `homelab-deploiements` (succès en priorité basse, échec en priorité haute).
Métriques : `homelab_deploiement_succes` et `homelab_deploiement_dernier_timestamp_seconds` (collecteur textfile de node_exporter).

## Installation
### 1. Secrets (sur le PC)
```bash
openssl rand -hex 32                          # secret partagé : à noter pour l'étape 3
sops compose/webhook/secrets.sops.env         # décommenter WEBHOOK_SECRET et NTFY_TOKEN (token du compte « scripts »)
```
Le compte ntfy `scripts` a déjà le droit `homelab-*:wo` : rien à changer dans ntfy. S'abonner à `homelab-deploiements` sur le téléphone.
Commit + push (le déploiement automatique n'existe pas encore : la suite est manuelle).

### 2. Mini PC
```bash
cd ~/Homelab && git pull
mkdir -p compose/webhook/data/declencheur ~/logs
scripts/compose-up.sh webhook
scripts/deploiement-auto.sh --essai           # doit répondre « Déjà à jour »
crontab -e
# * * * * * $HOME/Homelab/scripts/deploiement-auto.sh --cron >> $HOME/logs/deploiement-auto.log 2>&1
```

### 3. Cloudflare
Zero Trust → Networks → Tunnels → *homelab* → Public Hostname → Add : `deploiement` / `<domaine>`,
service `HTTPS` — `traefik:8443`, *Origin Server Name* = `deploiement.<domaine>` (comme les autres noms).
Ne pas le mettre derrière Cloudflare Access : GitHub ne sait pas s'y authentifier.

Règle WAF (défense en profondeur) : Security → WAF → Custom rules → Create rule, nom `Webhook GitHub uniquement`,
*Edit expression*, action **Block**, à placer **en premier** :
```
(http.host eq "deploiement.<domaine>" and (
  not ip.src in {9.234.106.48/28 9.234.98.160/28 9.234.98.176/28 192.30.252.0/22 185.199.108.0/22
                 140.82.112.0/20 143.55.64.0/20 2a0a:a440::/29 2606:50c0::/32}
  or http.request.method ne "POST"
  or http.request.uri.path ne "/hooks/homelab"))
```
Plages = clé `hooks` de `https://api.github.com/meta` (relevées en octobre 2026). GitHub les change parfois : en cas de 403
dans *Recent Deliveries* avec une page Cloudflare, comparer avec `curl -s https://api.github.com/meta | jq .hooks`
et Security → Events. Plus tard : la gérer avec le provider Terraform `cloudflare/cloudflare` (objectif tf).

### 4. GitHub
Dépôt → Settings → Webhooks → Add webhook :

| Champ | Valeur |
|---|---|
| Payload URL | `https://deploiement.<domaine>/hooks/homelab` |
| Content type | `application/json` |
| Secret | la valeur de `WEBHOOK_SECRET` |
| Events | *Just the push event* |

Le *ping* envoyé à la création répond **403** : normal, le hook n'accepte que les événements `push`.

## Vérifier
Pousser un petit changement sur une stack de la liste blanche, puis :
```bash
docker logs --tail 20 webhook                 # « 200 » sur /hooks/homelab
tail -f ~/logs/deploiement-auto.log
```
GitHub → Settings → Webhooks → *Recent Deliveries* montre la réponse de chaque push (et permet de le rejouer).

## Dépannage
| Symptôme | Cause probable |
|---|---|
| GitHub : 403 sur un push | Secret différent entre GitHub et `WEBHOOK_SECRET`, ou push sur une autre branche que `main` |
| GitHub : 502 / 530 | Conteneur webhook arrêté, ou nom public absent du tunnel / mauvais *Origin Server Name* |
| 200 côté GitHub mais rien ne se passe | Ligne crontab absente (`crontab -l`) ; droits de `data/declencheur` (doit être 1000:1000) |
| « modifications locales sur le Mini PC » | Un fichier a été modifié directement sur le serveur : `git diff`, puis le committer depuis le PC ou `git checkout -- <fichier>` |
| Pas de notification | `NTFY_TOKEN` absent des secrets, ou clé SOPS non lisible par l'utilisateur du cron |

Lancer un déploiement sans push : `scripts/deploiement-auto.sh` (vérifie GitHub immédiatement).

## Sécurité
- Quiconque peut pousser sur `main` peut exécuter du code sur le Mini PC : 2FA sur le compte GitHub, et une règle de branche
  qui interdit le force push sur `main` (Settings → Rules).
- Les stacks critiques (Traefik, tunnel, Arcane, Vaultwarden, ntfy, webhook) restent hors liste blanche : une erreur y couperait l'accès
  ou la notification qui la signale.

## Plus tard
Même principe en mode « pull » avec Flux ou Argo CD quand le homelab passera sur K3s (objectif GitOps de la feuille de route).
