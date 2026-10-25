# Agent de dépannage (Claude Code)

Quand un conteneur plante, l'agent lit les journaux et les métriques, trouve la cause, relance ce qui est autorisé,
propose le correctif durable en **Pull Request** et envoie un **rapport** sur ntfy. Chaque matin à 07:30, il fait le
bilan des dernières 24 h.

Il tourne avec l'**abonnement Claude Pro** (token OAuth de `claude setup-token`) : **aucune clé API, aucune facturation
à l'usage**. Vue d'ensemble, sécurité et limites : [docs/15-agent-depannage.md](../../docs/15-agent-depannage.md).

```
Alertmanager ──(Conteneur*, ServiceInjoignable…)──► agent ──► claude -p (Sonnet, permissions « dontAsk »)
 + healthchecks Docker « unhealthy »                  │            │ lit : API Docker (GET filtré), Loki, Prometheus, dépôt
                                                      │            │ agit : dépose une demande ──► scripts/agent-actions.sh (hôte, cron)
                                                      │            │                               └─► compose-up.sh <stack> restart|up
                                                      │            └ corrige un fichier du clone ──► branche agent/… ──► PR GitHub
                                                      └──► rapport : ntfy (topic homelab-agent) + data/rapports/<id>.md
```

## Fichiers
| Fichier | Rôle |
|---|---|
| `compose.yaml` | conteneur `agent` + `socket-proxy-agent` (API Docker en lecture, filtrée) |
| `Dockerfile` | Debian slim + binaire natif Claude Code (version figée) + Python + git |
| `agent/agent.py` | récepteur d'alertes, file d'attente, lancement de Claude, contrôle du correctif, PR, rapport, ntfy |
| `agent/outils.py` | les seules commandes autorisées à Claude : `conteneurs`, `conteneur`, `journaux`, `evenements`, `loki`, `prom`, `hote`, `historique`, `action` |
| `agent/consignes/CLAUDE.md` | consignes de l'agent (méthode, règles du dépôt, sécurité) |
| `agent/consignes/settings.json` | permissions de Claude Code (liste blanche d'outils et de chemins) |
| `agent/consignes/incident.md`, `quotidien.md` | modèles de demande |
| `../agent-actions.txt` | liste blanche des stacks/actions que l'hôte accepte d'exécuter |
| `../../scripts/agent-actions.sh` | exécute les demandes sur l'hôte (cron) |

## Installation

### 1. Token de l'abonnement (une fois par an)
`claude setup-token` ouvre une connexion au compte Claude **Pro** et affiche un token `sk-ant-oat01-…` valable 1 an.
Sur le PC (si Claude Code y est installé) ou, après l'étape 3, sur le Mini PC sans rien installer :
```bash
docker run --rm -it --entrypoint claude homelab/agent:2.1.303 setup-token
```
Ouvrir le lien affiché, se connecter avec le compte **Pro personnel**, coller le code. Noter le token.

### 2. Secrets (sur le PC)
```bash
openssl rand -hex 32                                   # jeton Alertmanager ↔ agent
sops compose/agent/secrets.sops.env                    # décommenter et remplir les 5 variables
sops compose/monitoring/secrets.sops.env               # ajouter AGENT_TOKEN_ALERTMANAGER=<même valeur>
```
- `NTFY_TOKEN` : token du compte ntfy **scripts** (déjà `homelab-*:wo`, rien à changer dans ntfy).
  S'abonner au topic `homelab-agent` sur le téléphone.
- `GITHUB_TOKEN` : GitHub → Settings → Developer settings → *Fine-grained tokens* → *Generate* :
  *Repository access* = **Only select repositories** → `Doxah/Homelab` ; *Permissions* → **Contents : Read and write**,
  **Pull requests : Read and write** (rien d'autre) ; expiration 1 an. Sans ce token, les correctifs sont gardés
  en `.patch` dans `data/rapports/`.
- `DOCKER_GID` : `getent group docker | cut -d: -f3` sur le Mini PC (même valeur que dans monitoring).

⚠ Commiter **dans le même commit** la modification de `compose/monitoring/secrets.sops.env` et celles de
`compose/monitoring/` : la stack monitoring est redéployée automatiquement et refuse de démarrer sans
`AGENT_TOKEN_ALERTMANAGER`.

### 3. GitHub : protéger `main`
Le token peut écrire dans le dépôt : `main` doit refuser les push directs pour que tout passe par une PR relue.
Dépôt → Settings → Rules → Rulesets → *New branch ruleset* : nom `main protégée`, *Enforcement* **Active**,
*Target* = branche par défaut, cocher **Restrict deletions**, **Require a pull request before merging**
(0 approbation requise : tu merges toi-même), **Block force pushes**. *Bypass list* : ton compte (pour continuer
à pousser directement depuis le PC).

### 4. Mini PC
```bash
cd ~/Homelab && git pull
mkdir -p compose/agent/data/{home,depot,rapports,etat,actions/demandes,actions/resultats} ~/logs
ls compose/backrest/data/backrest/etat-hooks compose/monitoring/data/textfile   # doivent exister (montés par l'agent)
scripts/compose-up.sh monitoring up -d                # nouveau receiver + règles (si pas déjà fait par le déploiement auto)
scripts/compose-up.sh agent up -d --build
docker logs agent                                     # « agent démarré »
crontab -e
# * * * * * $HOME/Homelab/scripts/agent-actions.sh --cron >> $HOME/logs/agent-actions.log 2>&1
```

### 5. Tester
```bash
docker exec agent python3 /opt/agent/agent.py tester convertx    # faux incident sur un conteneur sain
docker exec agent python3 /opt/agent/agent.py quotidien          # rapport quotidien tout de suite
docker logs -f agent                                             # suivre l'exécution
ls compose/agent/data/rapports/                                  # rapports Markdown
```
Test complet : `docker stop convertx` → Alertmanager déclenche `ConteneurDisparu` après 2 min → l'agent relance
convertx et envoie son rapport ~2 min plus tard.

## Réglages (environment du compose.yaml)
| Variable | Défaut | Effet |
|---|---|---|
| `MODELE` / `MODELE_QUOTIDIEN` | `sonnet` | `opus` = diagnostics plus poussés mais consomme bien plus vite le quota Pro |
| `MAX_DIAGNOSTICS_JOUR` | 8 | au-delà, les alertes ne lancent plus l'agent jusqu'au lendemain (notification) |
| `DELAI_ENTRE_DIAGNOSTICS_MIN` | 120 | une même alerte sur un même conteneur n'est re-diagnostiquée qu'après ce délai |
| `DELAI_REGROUPEMENT_S` | 90 | alertes arrivées ensemble (stack entière tombée) = un seul diagnostic |
| `TOURS_MAX_*`, `DUREE_MAX_MIN` | 40 / 50, 20 | bornes d'une exécution |
| `HEURE_RAPPORT_QUOTIDIEN` | `07:30` | vide = pas de rapport quotidien |
| `SURVEILLER_UNHEALTHY` | 1 | diagnostic aussi quand un healthcheck Docker passe « unhealthy » |
| `RECHERCHE_WEB` | 1 | autorise WebSearch (bugs connus, notes de version) ; jamais WebFetch |
| `ALERTES_GEREES` | `Conteneur.*\|ServiceInjoignable\|…` | à garder cohérent avec la route `agent` d'Alertmanager |

Autoriser une nouvelle action : ajouter la stack dans [`compose/agent-actions.txt`](../agent-actions.txt) (commit sur main).
Ne pas déclencher l'agent pour un arrêt volontaire : poser un **silence** dans Alertmanager (comme pour le téléphone).
Les conteneurs arrêtés par Backrest pendant la sauvegarde sont ignorés automatiquement.

## Quota de l'abonnement
L'agent partage les limites de ton abonnement Pro (fenêtres de 5 h et plafond hebdomadaire) avec ton usage de
Claude.ai, Cowork et Claude Code. Un diagnostic Sonnet ≈ 10 à 20 tours (≈ 1 min) ; le rapport quotidien un peu plus.
Si la limite est atteinte, l'agent prévient sur ntfy et reporte le diagnostic d'une heure (une seule fois).
Le mode `claude -p` est couvert par l'abonnement à la date d'écriture (octobre 2026). Anthropic a annoncé puis suspendu
en 2026 un passage de cet usage sur des crédits séparés : en cas de changement, l'agent continuera de refuser toute clé
API ; il faudra réévaluer.

## Dépannage
| Symptôme | Piste |
|---|---|
| `ERREUR : ANTHROPIC_API_KEY défini(es)` | retirer la variable : l'agent refuse toute facturation à l'usage |
| rapport « Diagnostic interrompu » / 401 | token expiré ou révoqué : refaire `claude setup-token`, mettre à jour le secret |
| `pas de réponse de l'hôte après 180 s` | ligne cron de `scripts/agent-actions.sh` absente ; `~/logs/agent-actions.log` |
| `HTTP 403` dans les outils | appel non autorisé par `socket-proxy-agent` (`-allowGET`) |
| rien ne se passe sur une alerte | `docker logs agent` : jeton refusé, alerte hors `ALERTES_GEREES`, anti-rebond, conteneur arrêté par Backrest |
| correctif « REFUSÉ par les garde-fous » | IP/domaine en clair, fichier protégé ou trop gros : `data/rapports/<id>.refuse.patch` |

Transcriptions complètes (chaque commande lancée par Claude et sa sortie) : `data/etat/journaux/<id>.jsonl`.
