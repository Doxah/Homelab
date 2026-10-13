# 10 — Gestion des secrets (SOPS + age)

Les secrets sont **chiffrés dans le dépôt** avec [SOPS](https://getsops.io/) et des clés [age](https://github.com/FiloSottile/age). Seules les valeurs sont chiffrées : les noms de variables restent lisibles, donc les diffs Git restent utiles.

Pourquoi SOPS : il fonctionne avec Docker Compose aujourd'hui, Ansible (collection `community.sops`) et Flux sur Kubernetes plus tard. Un seul outil pour tout le parcours.

## Clés
| Clé | Où vit la clé privée | Rôle |
|---|---|---|
| PC Windows | `%AppData%\sops\age\keys.txt` | Créer et modifier les secrets |
| Mini PC | `~/.config/sops/age/keys.txt` | Déchiffrer au déploiement |

- Les clés **publiques** sont dans [`.sops.yaml`](../.sops.yaml). Tout fichier est chiffré pour toutes les clés listées.
- Les clés **privées** ne sont jamais dans le dépôt (`keys.txt` est dans le `.gitignore`).
- La clé du PC est sauvegardée hors du homelab : si le homelab tombe, il faut pouvoir la récupérer sans lui.

## Installation

Windows :
```powershell
winget install FiloSottile.age
winget install SecretsOPerationS.SOPS
mkdir "$env:APPDATA\sops\age"
age-keygen -o "$env:APPDATA\sops\age\keys.txt"
```

Debian (Mini PC) :
age est dans les dépôts Debian, **SOPS ne l'est pas** (`apt install sops` échoue) : il s'installe depuis le paquet `.deb` des releases GitHub.

```bash
sudo apt install age

# SOPS : dernier .deb publié sur https://github.com/getsops/sops/releases
SOPS_VERSION=$(curl -s https://api.github.com/repos/getsops/sops/releases/latest | grep -oP '"tag_name": "\K[^"]+')
curl -LO "https://github.com/getsops/sops/releases/download/${SOPS_VERSION}/sops_${SOPS_VERSION#v}_amd64.deb"
sudo apt install ./sops_${SOPS_VERSION#v}_amd64.deb && rm sops_*_amd64.deb
sops --version

# Clé age : avec l'utilisateur qui lance les stacks (pas root)
mkdir -p ~/.config/sops/age && chmod 700 ~/.config/sops/age
age-keygen -o ~/.config/sops/age/keys.txt && chmod 600 ~/.config/sops/age/keys.txt
```

La clé est cherchée dans le `~/.config` de l'utilisateur courant : si elle a été créée pour `administrateur`, lancer `sops` et `scripts/compose-up.sh` avec ce compte, pas en root.

`age-keygen` affiche la clé publique (`age1...`) : la reporter dans `.sops.yaml`.

## Utilisation
```bash
sops compose/<stack>/secrets.sops.env      # créer ou modifier (ouvre l'éditeur)
sops -d compose/<stack>/secrets.sops.env   # afficher en clair
scripts/compose-up.sh <stack>              # lancer la stack avec ses secrets
```

Sous Windows, choisir l'éditeur : `$env:EDITOR = "code --wait"` (ou `notepad`).

`scripts/compose-up.sh` utilise `sops exec-env` : les secrets sont passés en variables d'environnement à `docker compose`, sans fichier `.env` en clair sur le disque.

## Fichiers de secrets pré-remplis
Une nouvelle stack est livrée avec son `secrets.sops.env` **déjà chiffré**, contenant une ligne commentée par variable attendue :
```dotenv
# GLPI_URL=https://glpi.example.org
# GLPI_APP_TOKEN=<jeton du client API>
```
SOPS chiffre aussi les commentaires (le hook pre-commit est satisfait) et seules les clés publiques sont nécessaires pour créer le fichier.
Pour le compléter : `sops <fichier>`, décommenter chaque ligne, remplacer la valeur. Tant qu'une variable reste commentée, `${VAR:?}` bloque le lancement.

## Convention de nommage
- Tout fichier chiffré contient `.sops.` dans son nom : `secrets.sops.env`, `values.sops.yaml`.
- Une stack = un `secrets.sops.env` à côté de son `compose.yaml`. Voir [`compose/_modele/`](../compose/_modele/).

## Garde-fous
[`.pre-commit-config.yaml`](../.pre-commit-config.yaml) bloque le commit si :
- un fichier `*.sops.*` n'est pas chiffré ;
- gitleaks détecte un secret (token, mot de passe, clé) dans un fichier en clair ;
- une clé privée est ajoutée.

```bash
pip install pre-commit
pre-commit install
pre-commit run --all-files
```

### Fins de ligne (CRLF)
Sous Windows, VS Code enregistre par défaut en CRLF. SOPS conserve alors le `\r` dans la valeur déchiffrée (`BIND_IP=127.0.0.1\r` → `invalid IP address`). Le fichier chiffré, lui, ne montre rien : un hook de commit ne peut pas le détecter. Trois protections :
1. **Éditeur** : [`.editorconfig`](../.editorconfig) + [`.vscode/settings.json`](../.vscode/settings.json) (`files.eol: "\n"`). `sops edit` ouvre un fichier temporaire hors du dépôt : mettre aussi `"files.eol": "\n"` dans les paramètres **utilisateur** de VS Code.
2. **Git** : [`.gitattributes`](../.gitattributes) force LF (`*.sops.*`, `*.sh`, `*.ps1`) et le hook `mixed-line-ending` corrige les autres fichiers.
3. **Lancement** : [`scripts/compose-up.sh`](../scripts/compose-up.sh) refuse de démarrer si une valeur déchiffrée contient un `\r` et affiche le nom des variables concernées (jamais leur valeur).

Diagnostic : `sops decrypt <fichier> | cat -A` (un `^M$` en fin de ligne = CRLF). Correction : `sops edit <fichier>`, cliquer sur `CRLF` dans la barre d'état de VS Code, choisir `LF`, enregistrer.

## Ajouter ou révoquer une clé
1. Modifier la liste dans `.sops.yaml`.
2. Rechiffrer chaque fichier : `sops updatekeys <fichier>`.
3. En cas de clé compromise : **changer aussi les secrets eux-mêmes**. Une clé révoquée peut toujours déchiffrer les anciennes versions présentes dans l'historique Git.

## Variables communes
`compose/commun.sops.env` (chiffré) contient les valeurs partagées par toutes les stacks (`DOMAIN`, `BIND_IP`).
`scripts/compose-up.sh` les exporte avant de lancer `sops exec-env` sur le `secrets.sops.env` de la stack,
dont les valeurs restent prioritaires en cas de doublon.
